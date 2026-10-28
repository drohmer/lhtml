"""What the parser of the tree (tree.py) reads with: the zones LHTML never
transforms, replaced by placeholders (ProtectionStores), the refusals of the
syntax removed in 3.0 (whether a `::` is a tag: tag_parser.py; the line
breaks option: render.py, it reads the nodes).

The kinds of stored content are listed in ProtectionStores; they become the
opaque leaves of the tree (code, inline code, mathematics, raw HTML).
"""

import bisect
import re
from dataclasses import dataclass, field

from .tag_parser import Unclosed, adjust_bare_tag, bare_tag, extract_bracket_elements, is_tag_boundary, tag_name_before
from .code import known_language, unknown_language_message
from .errors import LHTMLParseError, quote, warn
from .patterns import (
    protected_blocks, zones_in,
    HEADING,
    INCLUDE, REMOVED_COMMENT, REMOVED_VERBATIM, TAG_MARKER,
    PLACEHOLDER_CHAR, PLACEHOLDER, EVENT_CHAR,
    make_placeholder,
)


@dataclass
class ProtectionStores:
    """The text each placeholder hides, as written, by kind:

    C: code blocks
    R: raw zones: HTML tags, comments, <script>/<style>, math
    I: inline code
    U: URL of link::/img::/video::/videoplay:: tags (and of url macros)
    A: LHTML styles, classes/IDs and HTML attributes

    The kinds are kept apart on purpose: they are the opaque leaves of the
    document tree (tree.py: code with its language, raw HTML, math, inline
    code), or text the tree keeps as written (a URL, an attribute value).
    A text may hold placeholders itself (a group holding raw HTML).
    """
    written: dict = field(default_factory=lambda: {kind: [] for kind in 'CRIUA'})

    def add(self, kind, written):
        store = self.written[kind]
        store.append(written)
        return make_placeholder(kind, len(store) - 1)

    def hidden(self, m):
        """The text a placeholder (its match) hides, its placeholders kept."""
        return self.written[m.group(1)][int(m.group(2))]

    def original(self, text):
        """`text` with its placeholders replaced by what they hide, as written."""
        return PLACEHOLDER.sub(lambda m: self.original(self.hidden(m)), text)

    def locate(self, text, offset):
        """(line, column) of `offset` of the prepared `text` in the source."""
        return position(self.original(text[:offset]))


def position(before):
    """(line, column), 1-based, of the place that `before`, the text before it, ends at."""
    return before.count('\n') + 1, len(before) - before.rfind('\n')


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


def code_language(header):
    m = re.search(r'\[([^\[\]\n]*)\]', header)
    return m.group(1) if m else ''


# ---------------------------------------------------------------------------
# Protected zones (raw HTML, inline code, URLs, math)
# ---------------------------------------------------------------------------

def url_and_closing_marks(url, marks):
    """A URL ends before a final `**` or `__` that closes a bold or an
    italic opened before its tag on its line (`**img::a.png**`); otherwise
    they are part of it (`link::...#object.__init__`). `marks`: the number
    of each written before the tag on its line."""
    after, marks = '', dict(marks)
    while True:                         # __**img::a.png**__: each closing pair in turn
        for mark in ('**', '__'):
            if url.endswith(mark) and len(url) > 2 and marks[mark] % 2 == 1:
                url, after = url[:-2], mark + after
                marks[mark] -= 1        # this one is closed now
                break
        else:
            return url, after


class MarksOnLine:
    """The line of a place, and the number of `**` and of `__` on its line
    before it, counted as the text is read left to right: each character
    once (a long line of URLs, many code blocks: linear)."""

    def __init__(self, text, start=0, line=1):
        """Read from `start`, the start of a line, the line `line`."""
        self.text, self.checked, self.at = text, start, {'**': start, '__': start}
        self.counts = {'**': 0, '__': 0}
        self.line, self.line_start = line, start
        self.zones = []                 # (start, end) of the zones read: their marks are none

    def skip(self, start, end):
        """A zone read (inline code, a comment...): the marks it holds are
        no bold nor italic (`**` x img::a.png**). In order, left to right."""
        if end > start:
            self.zones.append((start, end))

    def _read(self, position):
        """Up to `position`: its line and where it starts."""
        text = self.text
        newline = text.rfind('\n', self.checked, position)
        if newline != -1:               # a new line: counted from its start
            self.line += text.count('\n', self.checked, position)
            self.line_start = newline + 1
            self.at = {'**': newline + 1, '__': newline + 1}
            self.counts = {'**': 0, '__': 0}
        self.checked = position

    def place(self, position):
        """(line, column), 1-based, of a place."""
        self._read(position)
        return self.line, position - self.line_start + 1

    def before(self, position):
        text = self.text
        self._read(position)
        for mark in self.counts:
            while (found := text.find(mark, self.at[mark], position)) != -1:
                k = bisect.bisect_right(self.zones, (found, len(text))) - 1
                if k >= 0 and self.zones[k][0] <= found < self.zones[k][1]:     # in a zone: none
                    self.at[mark] = self.zones[k][1]
                    continue
                self.counts[mark] += 1
                self.at[mark] = found + 2
            self.at[mark] = max(self.at[mark], position - 1)    # read: not again (one may end there)
        return self.counts


def process_protect(text, stores, url_tags, lexers=None):
    """Replace zones that LHTML must not transform with placeholders.

    Protected (the leftmost zone wins): HTML comments, <script>/<style>
    blocks, inline code, URLs of link::/img::/video:: tags (and of the
    tags `url_tags`: the macros that take a URL), math
    (\\(...\\), \\[...\\]) and HTML tags themselves (so attribute values
    are never modified), and code blocks, in the same left-to-right scan.
    Text between HTML tags is still processed. Jinja expressions,
    statements and comments are opaque.
    """
    marks = MarksOnLine(text)

    def _protect(m):
        if m.group('code') is not None:
            # the text is the source here: an offset in it is a place
            _refuse_include(m.group('body'), lambda k: position(text[:m.start('body') + k]))
            header = m.group('header')
            language = code_language(header)
            if not known_language(language, lexers):
                warn(unknown_language_message(language, lexers), marks.place(m.start()), stacklevel=6)
            groups = header[header.index(']') + 1:]
            if groups.strip():              # (.big)[color:red]: a code block has none
                warn(f'code::[{language}]{groups}: a code block takes its language only, {groups} is ignored',
                     marks.place(m.start()), stacklevel=6)
            marks.skip(m.start(), m.end())
            return stores.add('C', m.group(0))
        if m.group('icode') is not None:
            marks.skip(m.start(), m.end())
            return stores.add('I', m.group(0))
        if m.group('url') is not None:
            url = m.group('url')
            if url.endswith(('**', '__')):      # the marks before it on its line, counted only then
                url, after = url_and_closing_marks(url, marks.before(m.start()))
            else:
                after = ''
            marks.skip(m.start(), m.end() - len(after))
            return m.group('urltag') + stores.add('U', url) + after
        marks.skip(m.start(), m.end())
        return stores.add('R', m.group(0))
    parts, prev = [], 0
    for m in zones_in(protected_blocks(tuple(url_tags)), text):
        parts += [text[prev:m.start()], _protect(m)]
        prev = m.end()
    parts.append(text[prev:])
    return ''.join(parts)


def process_protect_attributes(text, stores):
    """Hide attribute groups from formatting, keeping link labels active."""
    def _heading(m):
        if not m.group(2):
            return m.group(0)
        return f'{m.group(1)}({stores.add("A", m.group(2))}) {m.group(3)}'
    text = HEADING.sub(_heading, text)

    parts, prev, read = [], 0, 0        # read: the end of the last element (its :: are its word, as in parse)
    unclosed = Unclosed()
    for m in TAG_MARKER.finditer(text):
        if m.start() < max(prev, read):
            continue
        tag = tag_name_before(text, m.start())
        # a :: glued to a word is no tag: decided before its element is read (a::a::a...: linear)
        if tag in ('include', 'code') or not is_tag_boundary(text, m.start() - len(tag), tag):
            continue
        is_tag, element = bare_tag(text, m) if not tag else (True, None)
        if not is_tag:
            continue
        if element is None:
            try:
                element = unclosed.extract(text, tag, m.start() - len(tag), m.end())
            except LHTMLParseError:
                continue
            if not tag and not adjust_bare_tag(text, m, element):
                continue
        read = element.end
        for kind, start, end in element.groups:
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
                              f'{{# ... #}} or an HTML comment <!-- ... --> (near {quote(text, m.start(), m.end() + 30)!r})',
                              *stores.locate(text, m.start()))
    for m in REMOVED_VERBATIM.finditer(text):
        if m.group(1) is None or stores.written['A'][int(m.group(1))] == '':     # verbatim::[] (not verbatim::[abc])
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
        name = extract_bracket_elements(text, 'include', m.start(), m.end()).text
    except LHTMLParseError:
        name = text[m.end():].split(None, 1)[0] if text[m.end():].strip() else ''
    raise LHTMLParseError(
        f'include::{name} was removed in LHTML 3.0 (LHTML reads no file): include '
        f'the file before calling LHTML, with Jinja {{% include "{name}" %}} for instance',
        *locate(m.start()))


def process_prepare(text, stores, url_tags, lexers=None):
    """Replace code blocks and protected zones (HTML, inline code,
    URLs, math, attributes) by placeholders; `url_tags`: the tags whose
    URL is kept as written. Raises LHTMLParseError on
    an include:: directive (removed in 3.0)."""
    text = process_protect(text, stores, url_tags, lexers)
    text = process_protect_attributes(text, stores)
    _refuse_include(text, lambda offset: stores.locate(text, offset))
    _refuse_removed(text, stores)   # after the groups are hidden: '::#' in an attribute is text
    return text


