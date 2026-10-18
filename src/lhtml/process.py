"""What the parser of the tree (tree.py) reads with: the zones LHTML never
transforms, replaced by placeholders (ProtectionStores), the refusals of the
syntax removed in 3.0, and the rules that decide whether a `::` is a tag
(the line breaks option is in render.py: it reads the nodes).

The kinds of stored content are listed in ProtectionStores; they become the
opaque leaves of the tree (code, inline code, mathematics, raw HTML).
"""

import contextvars
import re
import warnings
from dataclasses import dataclass, field

from .tag_parser import extract_bracket_elements, _TAG_NAME_BEFORE, _MAX_TAG_NAME
from .code import known_language, unknown_language_message
from .errors import LHTMLParseError, LHTMLWarning
from .patterns import (
    PROTECTED, PROTECTED_BLOCKS, protected_blocks,
    HEADING,
    INCLUDE, REMOVED_COMMENT, REMOVED_VERBATIM, TAG_MARKER, SPACER,
    PLACEHOLDER_CHAR, PLACEHOLDER, EVENT_CHAR,
    regex_transform, make_placeholder,
)


@dataclass
class ProtectionStores:
    """Content replaced by placeholders during processing, by kind:

    C: code blocks, kept as (header, body) and highlighted at the end
    R: raw zones: HTML tags, comments, <script>/<style>, math
    I: inline code (content with < and > escaped)
    U: URL of link::/img::/video::/videoplay:: tags
    A: LHTML styles, classes/IDs and HTML attributes

    The kinds are kept apart on purpose: they are the opaque leaves of the
    document tree (tree.py: code with its language, raw HTML, math, inline
    code), or text the tree keeps as written (a URL, an attribute value).
    """
    C: list = field(default_factory=list)
    R: list = field(default_factory=list)
    I: list = field(default_factory=list)
    U: list = field(default_factory=list)
    A: list = field(default_factory=list)  # LHTML attribute group contents
    # the text each placeholder hides, as written: where a problem is (`locate`)
    sources: dict = field(default_factory=lambda: {kind: [] for kind in 'CRIUA'})

    def add(self, kind, entry, source=None):
        store = getattr(self, kind)
        store.append(entry)
        self.sources[kind].append(entry if source is None else source)
        return make_placeholder(kind, len(store) - 1)

    def original(self, text):
        """`text` with its placeholders replaced by what they hide, as written."""
        return PLACEHOLDER.sub(lambda m: self.original(self.sources[m.group(1)][int(m.group(2))]), text)

    def locate(self, text, offset):
        """(line, column) of `offset` of the prepared `text` in the source."""
        return position(self.original(text[:offset]))


def position(before):
    """(line, column), 1-based, of the place that `before`, the text before it, ends at."""
    return before.count('\n') + 1, len(before) - before.rfind('\n')


# The problems of the parse running in this context (a thread, a task): each
# parse has its own list, no global state is changed (warnings.catch_warnings is)
PROBLEMS = contextvars.ContextVar('lhtml_problems', default=None)


def _warn(message, place, stacklevel=3):
    """A problem at `place`: (line, column), or an element (or Written) with
    them. Kept by the parse running (PROBLEMS), a warning outside one."""
    if isinstance(place, dict):
        place = place.get('line'), place.get('column')
    elif hasattr(place, 'line'):
        place = place.line, place.column
    problem = LHTMLWarning(message, *(place or (None, None)))
    problems = PROBLEMS.get()
    if problems is None:
        warnings.warn(problem, stacklevel=stacklevel)
    else:
        problems.append(problem)


# ---------------------------------------------------------------------------
# Input normalization
# ---------------------------------------------------------------------------

def normalize_input(text):
    """Normalize a source text: no BOM, LF line endings, no NUL character
    (which would be mistaken for a placeholder delimiter), no EVENT_CHAR
    (the mark of the document tree): each becomes U+FFFD."""
    if text.startswith('\ufeff'):
        text = text[1:]
    text = text.replace('\r\n', '\n').replace(PLACEHOLDER_CHAR, '\ufffd')
    if EVENT_CHAR in text:
        text = text.replace(EVENT_CHAR, '\ufffd')
    return text


def read_source(filename):
    """Read an LHTML source file (UTF-8, with or without BOM), normalized."""
    with open(filename, 'r', encoding='utf-8-sig') as fid:
        return normalize_input(fid.read())


def _code_language(header):
    m = re.search(r'\[([^\[\]\n]*)\]', header)
    return m.group(1) if m else ''


# ---------------------------------------------------------------------------
# Protected zones (raw HTML, inline code, URLs, math)
# ---------------------------------------------------------------------------

def escape_inline_code(content):
    """Escape < and > in inline code (& is kept so that entities written
    by hand, such as &lt;, still work)."""
    return content.replace('<', '&lt;').replace('>', '&gt;')


def render_inline_code(content):
    return f'<code class="code-inline">{content}</code>'


def _url_and_closing_marks(url, before):
    """A URL ends before a final `**` or `__` that closes a bold or an
    italic opened before its tag on its line (`**img::a.png**`); otherwise
    they are part of it (`link::...#object.__init__`)."""
    after = ''
    while True:                         # __**img::a.png**__: each closing pair in turn
        for mark in ('**', '__'):
            if url.endswith(mark) and len(url) > 2 and before.count(mark) % 2 == 1:
                url, after = url[:-2], mark + after
                before = before.replace(mark, '', 1)     # this one is closed now
                break
        else:
            return url, after


def process_protect(text, stores, blocks=False, url_tags=None):
    """Replace zones that LHTML must not transform with placeholders.

    Protected (the leftmost zone wins): HTML comments, <script>/<style>
    blocks, inline code, URLs of link::/img::/video:: tags (and of the
    tags `url_tags`: the macros that take a URL), math
    (\\(...\\), \\[...\\]) and HTML tags themselves (so attribute values
    are never modified). Text between HTML tags is still processed. Jinja
    expressions, statements and comments are opaque. With `blocks`, code
    blocks participate in the same left-to-right scan.
    """
    def _protect(m):
        if blocks and m.group('code') is not None:
            # the text is the source here: an offset in it is a place
            _refuse_include(m.group('body'), lambda k: position(text[:m.start('body') + k]))
            language = _code_language(m.group('header'))
            if not known_language(language):
                start = m.start()           # counted in place: a page may hold many blocks
                _warn(unknown_language_message(language),
                      (text.count('\n', 0, start) + 1, start - text.rfind('\n', 0, start)), stacklevel=6)
            return stores.add('C', (m.group('header'), m.group('body')), m.group(0))
        if m.group('icode') is not None:
            return stores.add('I', escape_inline_code(m.group('icode')), m.group(0))
        if m.group('url') is not None:
            url = m.group('url')
            if url.endswith(('**', '__')):      # the line before it, read only then (linear time)
                url, after = _url_and_closing_marks(url, text[text.rfind('\n', 0, m.start()) + 1:m.start()])
            else:
                after = ''
            return m.group('urltag') + stores.add('U', url) + after
        return stores.add('R', m.group(0))
    pattern = (protected_blocks(tuple(url_tags)) if url_tags is not None else PROTECTED_BLOCKS) \
        if blocks else PROTECTED
    return regex_transform(text, pattern, _protect)


def process_protect_attributes(text, stores):
    """Hide attribute groups from formatting, keeping link labels active."""
    def _heading(m):
        if not m.group(2):
            return m.group(0)
        return f'{m.group(1)}({stores.add("A", m.group(2))}) {m.group(3)}'
    text = regex_transform(text, HEADING, _heading)

    parts, prev = [], 0
    for m in TAG_MARKER.finditer(text):
        if m.start() < prev:
            continue
        found = _TAG_NAME_BEFORE.search(text, max(0, m.start() - _MAX_TAG_NAME), m.start())
        tag = found.group() if found else ''
        # a :: glued to a word is no tag: decided before its element is read (a::a::a...: linear)
        if tag in ('include', 'code') or not _is_tag_boundary(text, m.start() - len(tag), tag):
            continue
        try:
            element = extract_bracket_elements(text, m.end())
        except LHTMLParseError:
            continue
        for kind, start, end in element['groups']:
            if tag == 'link' and kind == '[]':      # the label of a link is text
                continue
            parts.append(text[prev:start])
            parts.append(stores.add('A', text[start:end]))
            prev = end
    parts.append(text[prev:])
    return ''.join(parts)


# ---------------------------------------------------------------------------
# Preparation of the text
# ---------------------------------------------------------------------------

def _refuse_removed(text, stores):
    """::# comments and verbatim:: blocks were removed in LHTML 3.0: raise
    rather than leave them as text, with the replacement in the message."""
    m = REMOVED_COMMENT.search(text)
    if m is not None:
        raise LHTMLParseError(f'::# comments were removed in LHTML 3.0: use a Jinja comment '
                              f'{{# ... #}} or an HTML comment <!-- ... --> (near {_context(text, m.start(), m.end() + 30)!r})',
                              *stores.locate(text, m.start()))
    for m in REMOVED_VERBATIM.finditer(text):
        if m.group(1) is None or stores.A[int(m.group(1))] == '':     # verbatim::[] (not verbatim::[abc])
            raise LHTMLParseError('verbatim:: was removed in LHTML 3.0: show text as it is with '
                                  'code::[text] ... code::[-], or write raw HTML directly',
                                  *stores.locate(text, m.start()))


def _refuse_include(text, locate):
    """include:: was removed in LHTML 3.0: LHTML reads no file. Raise where
    LHTML 2 would have expanded one, rather than leave the directive as text.
    `locate(offset)`: the (line, column) of an offset of `text`."""
    m = INCLUDE.search(text)
    if m is None:
        return
    try:
        name = extract_bracket_elements(text, m.end())['text']
    except LHTMLParseError:
        name = text[m.end():].split(None, 1)[0] if text[m.end():].strip() else ''
    raise LHTMLParseError(
        f'include::{name} was removed in LHTML 3.0 (LHTML reads no file): include '
        f'the file before calling LHTML, with Jinja {{% include "{name}" %}} for instance',
        *locate(m.start()))


def process_prepare(text, stores, url_tags=None):
    """Replace code blocks and protected zones (HTML, inline code,
    URLs, math, attributes) by placeholders; `url_tags`: the tags whose
    URL is kept as written (URL_TAGS by default). Raises LHTMLParseError on
    an include:: directive (removed in 3.0)."""
    text = process_protect(text, stores, blocks=True, url_tags=url_tags)
    text = process_protect_attributes(text, stores)
    _refuse_include(text, lambda offset: stores.locate(text, offset))
    _refuse_removed(text, stores)   # after the groups are hidden: '::#' in an attribute is text
    return text


# ---------------------------------------------------------------------------
# Tag elements (the :: system)
# ---------------------------------------------------------------------------

def check_is_closing_tag(element):
    """A bare :: (empty tag, span of exactly 2) is a closing tag."""
    return element['tag'] == '' and element['index_end'] - element['index_start'] == 2


def _refuse_explicit_closing(element):
    """::[-] and ::name[-] were removed in LHTML 3.0: a tag is closed by ::.
    On a named tag, x::[-] is a style '-' (as in LHTML 2): kept, with a
    warning, since it was most likely meant as a closing tag."""
    context = element.get('context', '')
    if element['tag'] == '':
        raise LHTMLParseError(f'{context}: ::name[-] and ::[-] were removed in LHTML 3.0: '
                              f'close a tag with ::', element.get('line'), element.get('column'))
    _warn(f'{context}: [-] is a style here, not a closing tag (close a tag with ::)', element, stacklevel=5)


def _context(text, start, end, max_len=40):
    """Short excerpt of the source around a tag, for warning messages."""
    excerpt = PLACEHOLDER.sub('…', text[start:min(end, start + max_len)])
    return excerpt.split('\n')[0]


def _is_tag_boundary(text, index, tag, last_tag_end=-1):
    """True if a tag (named, or bare :: when tag is '') may start at `index`.

    A tag name must not be glued to a preceding word (x.link::, std::a::).
    A bare :: must not follow an opening bracket or a word character, which
    leaves constructs like a[::2] or 2::3 untouched. A tag may always
    directly follow the previous tag.
    """
    if index == 0 or index == last_tag_end:
        return True
    ch = text[index - 1]
    if ch.isalnum() or ch in '_:':
        return False
    if tag:
        return ch not in '-.'
    return ch not in '[({'


def _adjust_bare_tag(text, m, element):
    """Adjust the extent of a bare :: tag. Returns False if it is not a tag.

    - '::nl' followed by other characters is a spacer ending after 'nl'.
    - '::' followed by punctuation (e.g. '::,' or '::**') is a closing tag.
    - A '::' between two protected zones (e.g. <span>::</span> in
      pre-highlighted C++), or glued after one and followed by a word,
      is not a tag.
    """
    after_placeholder = m.start() > 0 and text[m.start() - 1] == PLACEHOLDER_CHAR
    if after_placeholder and text[m.end():m.end() + 1] == PLACEHOLDER_CHAR:
        return False

    word = element['text']
    if SPACER.match(word):
        if element['index_end'] != m.end() + 2:
            element.update({'text': 'nl', '[]': '', '()': '', '{}': '',
                            'index_end': m.end() + 2})
        return True
    if after_placeholder and word[:1].isalnum():
        return False
    following = text[m.end():m.end() + 1]
    if following and not (following.isalnum() or following.isspace() or following in '[({'):
        element.update({'text': '', '[]': '', '()': '', '{}': '', 'index_end': m.end()})
    return True
