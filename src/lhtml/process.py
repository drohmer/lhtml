"""Core LHTML processing functions.

Each function transforms LHTML markup into HTML for one language
feature (headings, bold, lists, tags, etc.). The pipeline execution
order is managed by pipeline.py.

Content that must not be transformed is replaced early by placeholders
(see patterns.PLACEHOLDER) and restored at the end. The kinds of stored
content are listed in ProtectionStores.
"""

import re
import warnings
from dataclasses import dataclass, field

from .tag_parser import extract_bracket_elements
from .export_html import (
    export_html_element_class_and_id, export_html_generic,
)
from .code import export_html_code, known_language, unknown_language_message
from .errors import LHTMLParseError, LHTMLWarning
from .patterns import (
    PROTECTED, PROTECTED_BLOCKS,
    HEADING, BOLD, ITALIC,
    INCLUDE, REMOVED_COMMENT, REMOVED_VERBATIM, TAG_MARKER, SPACER,
    BLOCK_TAGS, LEADING_TAG, TRAILING_TAG, LEADING_PLACEHOLDER, TRAILING_PLACEHOLDER,
    JINJA_LINE, BLOCK_RAW, PREFORMATTED_TAG,
    PLACEHOLDER_CHAR, PLACEHOLDER,
    regex_transform, restore_from_index, make_placeholder,
)


@dataclass
class ProtectionStores:
    """Content replaced by placeholders during processing, by kind:

    C: code blocks, kept as (header, body) and highlighted at the end
    R: raw zones: HTML tags, comments, <script>/<style>, math
    I: inline code (content with < and > escaped)
    U: URL of link::/img::/video::/videoplay:: tags
    A: LHTML styles, classes/IDs and HTML attributes

    The kinds are kept apart on purpose: they are the opaque fragments of the
    document tree of a later version (code with its language, raw HTML,
    math, inline code, a URL or an attribute value), not just text to hide.
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

    def tag_positions(self, text):
        """(line, column) in the source of each `::` (TAG_MARKER) of the
        prepared `text`, in order. The passes before process_tag add lines
        (a heading, a list) but no `::`: the k-th `::` it reads is this k-th."""
        positions, line, column, previous = [], 1, 1, 0
        for m in TAG_MARKER.finditer(text):
            segment = self.original(text[previous:m.start()])
            if '\n' in segment:
                line += segment.count('\n')
                column = len(segment) - segment.rfind('\n')
            else:
                column += len(segment)
            positions.append((line, column))
            previous = m.start()
        return positions

    def restore(self, text, kind, render_fn=None):
        return restore_from_index(text, kind, getattr(self, kind), render_fn)


def position(before):
    """(line, column), 1-based, of the place that `before`, the text before it, ends at."""
    return before.count('\n') + 1, len(before) - before.rfind('\n')


def _warn(message, place, stacklevel=3):
    """A warning at `place`: (line, column), or an element with them."""
    if isinstance(place, dict):
        place = place.get('line'), place.get('column')
    warnings.warn(LHTMLWarning(message, *(place or (None, None))), stacklevel=stacklevel)


# ---------------------------------------------------------------------------
# Input normalization
# ---------------------------------------------------------------------------

def normalize_input(text):
    """Normalize a source text: no BOM, LF line endings, no NUL character
    (which would be mistaken for a placeholder delimiter)."""
    if text.startswith('\ufeff'):
        text = text[1:]
    return text.replace('\r\n', '\n').replace(PLACEHOLDER_CHAR, '\ufffd')


def read_source(filename):
    """Read an LHTML source file (UTF-8, with or without BOM), normalized."""
    with open(filename, 'r', encoding='utf-8-sig') as fid:
        return normalize_input(fid.read())


def _code_language(header):
    m = re.search(r'\[([^\[\]\n]*)\]', header)
    return m.group(1) if m else ''


def render_code_block(entry):
    """Highlight a stored (header, body) code block."""
    header, body = entry
    return export_html_code(body, _code_language(header), warn=False)   # warned at process_protect


# ---------------------------------------------------------------------------
# Protected zones (raw HTML, inline code, URLs, math)
# ---------------------------------------------------------------------------

def escape_inline_code(content):
    """Escape < and > in inline code (& is kept so that entities written
    by hand, such as &lt;, still work)."""
    return content.replace('<', '&lt;').replace('>', '&gt;')


def render_inline_code(content):
    return f'<code class="code-inline">{content}</code>'


def process_protect(text, stores, blocks=False):
    """Replace zones that LHTML must not transform with placeholders.

    Protected (the leftmost zone wins): HTML comments, <script>/<style>
    blocks, inline code, URLs of link::/img::/video:: tags, math
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
                _warn(unknown_language_message(language), position(text[:m.start()]), stacklevel=6)
            return stores.add('C', (m.group('header'), m.group('body')), m.group(0))
        if m.group('icode') is not None:
            return stores.add('I', escape_inline_code(m.group('icode')), m.group(0))
        if m.group('url') is not None:
            return m.group('urltag') + stores.add('U', m.group('url'))
        return stores.add('R', m.group(0))
    pattern = PROTECTED_BLOCKS if blocks else PROTECTED
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
        try:
            element = extract_bracket_elements(text, m.end())
        except LHTMLParseError:
            continue
        tag = element['tag']
        if tag in ('include', 'code') or not _is_tag_boundary(
                text, m.start() - len(tag), tag):
            continue
        for kind, start, end in element['groups']:
            if tag == 'link' and kind == '[]':      # the label of a link is text
                continue
            parts.append(text[prev:start])
            parts.append(stores.add('A', text[start:end]))
            prev = end
    parts.append(text[prev:])
    return ''.join(parts)


def process_unprotect(text, stores):
    """Restore the raw zones and URLs protected by process_protect."""
    text = stores.restore(text, 'A')
    text = stores.restore(text, 'R')
    return stores.restore(text, 'U')


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


def process_prepare(text, stores):
    """Replace code blocks and protected zones (HTML, inline code,
    URLs, math, attributes) by placeholders. Raises LHTMLParseError on an
    include:: directive (removed in 3.0)."""
    text = process_protect(text, stores, blocks=True)
    text = process_protect_attributes(text, stores)
    _refuse_include(text, lambda offset: stores.locate(text, offset))
    _refuse_removed(text, stores)   # after the groups are hidden: '::#' in an attribute is text
    return text


# ---------------------------------------------------------------------------
# Inline formatting
# ---------------------------------------------------------------------------

def process_bold(text):
    """Convert **text** to <strong>text</strong>."""
    return regex_transform(text, BOLD, lambda m: f'<strong>{m.group(1)}</strong>')


def process_italic(text):
    """Convert __text__ to <em>text</em>."""
    return regex_transform(text, ITALIC, lambda m: f'<em>{m.group(1)}</em>')


# ---------------------------------------------------------------------------
# Headings
# ---------------------------------------------------------------------------

def process_title(text, stores):
    """Convert = Title or =(.class) Title to <h1>Title</h1>, etc.

    The (.class #id) group protected by process_protect_attributes is
    resolved, and the generated attributes stay protected from inline
    formatting until process_unprotect.
    """
    def _heading(m):
        level = str(len(m.group(1)))
        class_id = m.group(2) or ''
        class_id = stores.restore(class_id, 'A').strip()
        title = m.group(3)
        if class_id:
            attrs = export_html_element_class_and_id(class_id)
            if attrs:
                attrs = stores.add('A', attrs)
            return f'<h{level}{attrs}>{title}</h{level}>\n'
        return f'<h{level}>{title}</h{level}>\n'
    return regex_transform(text, HEADING, _heading)


# ---------------------------------------------------------------------------
# Tag elements (the :: system)
# ---------------------------------------------------------------------------

def _warn_unmatched_closing(element):
    """Warn about a closing :: without opening tag; the source is kept."""
    _warn(f"Closing tag :: has no matching opening tag (near {element.get('context', '')!r})",
          element, stacklevel=5)
    return '', False


def check_is_closing_tag(element):
    """A bare :: (empty tag, span of exactly 2) is a closing tag."""
    return element['tag'] == '' and element['index_end'] - element['index_start'] == 2


def _dispatch_tag(element, tag_to_close, context, tags):
    """Dispatch a parsed tag element to the appropriate handler.

    Named tags go to their handler in `tags`. Unnamed tags (::) are closing
    tags, spacers or anonymous divs.
    """
    tag = element['tag']
    if element['[]'] == '-' and tag != 'link':     # link::url[-] is the text '-'
        _refuse_explicit_closing(element)

    if tag != '':
        handler = tags.get(tag)
        if handler is not None:
            return handler(element, tag_to_close, context)
        # Unrecognized tag — pass through
        return '', False

    if check_is_closing_tag(element):
        if not tag_to_close:
            return _warn_unmatched_closing(element)
        return '</' + tag_to_close.pop() + '>', True
    if element['text'] == 'nl':
        return '<div style="height:1em;"></div>', True
    if element['[]'] or element['()'] or element['{}'] or element['text']:
        return export_html_generic(element, 'div', tag_to_close), True
    return '', False


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


def process_tag(text, run_context, tags, resolve=None, positions=None):
    """Process all :: tag elements in text.

    Args:
        run_context: the ProcessingContext of the run, passed to the handlers.
        tags: the handlers of the named tags {name: handler}.
        resolve: function applied to the parsed fields before dispatch
            (used to restore protected URLs).
        positions: (line, column) in the source of each `::` of the text
            (ProtectionStores.tag_positions): an element gets its 'line' and
            'column', which its warnings and errors carry.
    """
    parts = []
    prev = 0
    last_tag_end = -1
    tag_to_close = []
    open_elements = []
    markers = list(TAG_MARKER.finditer(text))
    if positions is None or len(positions) != len(markers):
        positions = [(None, None)] * len(markers)

    for m, (line, column) in zip(markers, positions):
        if m.start() < prev:
            continue  # skip overlapping matches

        try:
            element = extract_bracket_elements(text, m.end())
        except LHTMLParseError as e:
            name = len(re.search(r'[A-Za-z][\w-]*$|$', text[max(0, m.start() - 64):m.start()]).group())
            _warn(f'{e} near {_context(text, m.start() - name, m.end() + 30)!r}',
                  (line, column - name if column else None))
            continue
        tag = element['tag']
        tag_start = m.start() - len(tag)
        if tag_start < prev:
            # The name found backwards belongs to the previous tag (::nl::[...])
            tag, tag_start = '', m.start()
            element.update({'tag': '', 'index_start': tag_start})
        if not _is_tag_boundary(text, tag_start, tag, last_tag_end):
            continue
        if not tag and not _adjust_bare_tag(text, m, element):
            continue
        element['line'] = line
        element['column'] = column - len(tag) if column else None
        context = text[tag_start:element['index_end']]
        if resolve is not None:
            context = resolve(context)
        element['context'] = _context(context, 0, len(context))
        if resolve is not None:
            for key in ('text', '[]', '()', '{}'):
                element[key] = resolve(element[key])

        depth = len(tag_to_close)
        html_out, is_real_tag = _dispatch_tag(element, tag_to_close, run_context, tags)
        del open_elements[len(tag_to_close):]
        open_elements.extend([element] * (len(tag_to_close) - depth))

        if is_real_tag:
            parts.append(text[prev:tag_start])
            parts.append(html_out)
            last_tag_end = element['index_end']
        else:
            parts.append(text[prev:element['index_end']])
        prev = element['index_end']

    for tag, element in zip(tag_to_close, open_elements):
        _warn(f"Tag <{tag}> is never closed (near {element['context']!r})", element)

    parts.append(text[prev:])
    return ''.join(parts)


# ---------------------------------------------------------------------------
# Line breaks option
# ---------------------------------------------------------------------------

def _is_block_placeholder(kind, idx, stores):
    """True if a protected zone is a block: code block, HTML comment,
    <script>/<style>, display math or block-level HTML tag."""
    if kind == 'C':
        return True
    if kind != 'R':
        return False
    entry = stores.R[idx]
    if BLOCK_RAW.match(entry) or JINJA_LINE.fullmatch(entry):
        return True
    m = LEADING_TAG.match(entry)
    return bool(m) and m.group(1).lower() in BLOCK_TAGS


def _is_structure_line(line, stores):
    """True if the line starts or ends with a block element, or is a Jinja statement."""
    if JINJA_LINE.fullmatch(line):
        return True
    for tag_re, ph_re in ((LEADING_TAG, LEADING_PLACEHOLDER), (TRAILING_TAG, TRAILING_PLACEHOLDER)):
        m = ph_re.search(line)
        if m and _is_block_placeholder(m.group(1), int(m.group(2)), stores):
            return True
        m = tag_re.search(line)
        if m and m.group(1).lower() in BLOCK_TAGS:
            return True
    return False


def _preformatted_depth_change(line, stores):
    """Count actual preformatted tags, never tag-like text inside raw zones."""
    tags = []
    for placeholder in PLACEHOLDER.finditer(line):
        if placeholder.group(1) == 'R':
            entry = stores.R[int(placeholder.group(2))]
            # An actual tag starts at the beginning of its stored zone.
            # Do not scan inside comments, scripts, attributes or Jinja.
            tags.append(PREFORMATTED_TAG.match(entry))
    # Tags generated by handlers (and direct calls without stores) are
    # not placeholders. Tokenize them so quoted attributes stay opaque.
    for zone in PROTECTED.finditer(line):
        if zone.group('tag') is not None:
            tags.append(PREFORMATTED_TAG.match(zone.group('tag')))
    return sum(-1 if tag.group(1) else 1 for tag in tags if tag is not None)


def process_line_breaks(text, stores):
    """Make the line breaks of the source visible with <br>.

    Lines that start or end with a block element (heading, list, div,
    code block, ...) are structure and are left alone. In each run of
    other lines, blank lines at the start and end of the run are ignored,
    and every line but the last one gets a <br>, blank lines included.
    The content of protected zones (code, math, scripts...) is not
    affected since it is still hidden in placeholders, nor is the content
    of <pre> and <textarea> elements, whose line breaks are already visible.
    """
    lines = text.split('\n')
    structure = []
    depth = 0
    for line in lines:
        change = _preformatted_depth_change(line, stores)
        structure.append(depth > 0 or change != 0 or _is_structure_line(line, stores))
        depth = max(0, depth + change)
    blank = [not line.strip() for line in lines]

    start = 0
    while start < len(lines):
        if structure[start]:
            start += 1
            continue
        end = start
        while end < len(lines) and not structure[end]:
            end += 1
        # run = lines[start:end], without leading/trailing blank lines
        first, last = start, end - 1
        while first <= last and blank[first]:
            first += 1
        while last >= first and blank[last]:
            last -= 1
        for k in range(first, last):
            lines[k] += '<br>'
        start = end
    return '\n'.join(lines)
