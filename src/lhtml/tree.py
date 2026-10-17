"""The document tree of LHTML: parse, then render (lhtml.run is both).

    document = parse(text, macros=None, tags=None)
    html     = render(document, line_breaks=False, media=None)

The tree holds headings, lists, bold and italic, the `::` elements, and the
zones LHTML never reads (code, inline code, mathematics, raw HTML, Jinja) as
opaque leaves. Every node has its `span`, the offsets of its source in the
text given to parse, and `line`, `column` exact by construction.

How it parses. The zones are found first (process.process_prepare), then
the stages read the text in order: headings, list lines, bold, italic, and
the `::` elements last. Each node a stage reads is recorded as events (its
opening, its closing), and each event becomes one character of the text the
next stages read (EVENT_CHAR), a boundary: a list line is a line that
starts with `* ` once the headings are read, the word of an element ends at
the end of a bold, a tag may follow it. These are the decisions of the text
passes LHTML 2 and 3.0 had, which wrote '<h1>', '<strong>' into the text
instead (the tree replaced them on 2026-10-17 with the same HTML on the
tests, a corpus of five projects and 80 000 fuzzed documents). Each
character keeps its origin, the source or an event; the tree is built from
the events, and `render` writes the HTML from the tree alone.

The nodes nest: nothing crosses. An element opened in a heading, a list
item, a bold or an italic span, and not closed there (its `::` elsewhere,
or none), is closed at the end of that container, with a warning; a `::`
that closes nothing (its element closed so, or the `::` inside a container
the element is not in) stays as text, with a warning. An italic that would
cross a bold, and an element whose text (a link label) would cross the end
of a heading, a list item, a bold or an italic, are not read: their source
stays as text, with a warning. The text passes wrote malformed HTML there
(<li><span>...</li>...</span>, <strong><em>...</strong>...</em>).
"""

from __future__ import annotations

import bisect
import re
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Callable

from .errors import LHTMLError, LHTMLParseError
from .export_html import SPACER, TAGS, Tag, export_html_element_class_and_id
from .macros import NAME_RE, NOT_ELEMENTS, registry_with_macros
from .patterns import (
    BOLD, EVENT_CHAR, HEADING, ITALIC, PLACEHOLDER, TAG_MARKER,
)
from .process import (
    ProtectionStores, normalize_input, process_prepare, process_unprotect,
    line_breaks as _with_line_breaks, render_inline_code, render_code_block, _code_language,
    _is_tag_boundary, _adjust_bare_tag, _context, _warn, check_is_closing_tag,
    _refuse_explicit_closing,
)
from .tag_parser import extract_bracket_elements, _TAG_NAME_BEFORE, _MAX_TAG_NAME


# ---------------------------------------------------------------------------
# The nodes
# ---------------------------------------------------------------------------

@dataclass(eq=False)
class Node:
    span: tuple = (0, 0)            # offsets in the text given to parse (end excluded)
    line: int | None = None         # 1-based, of span[0]
    column: int | None = None
    children: list = field(default_factory=list)

    @property
    def kind(self):
        return type(self).__name__

    def walk(self):
        """The node and its descendants, in document order (no recursion:
        a document may nest deeper than Python's recursion limit)."""
        stack = [self]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))


@dataclass(eq=False)
class Document(Node):
    problems: list = field(default_factory=list)    # LHTMLWarning, with their line and column
    stores: ProtectionStores | None = None          # the opaque zones, for render


@dataclass(eq=False)
class Text(Node):
    value: str = ''                 # as written
    raw: str = ''                   # with the placeholders of the zones it holds (render)


@dataclass(eq=False)
class Heading(Node):
    level: int = 1
    attributes: str = ''            # (.class #id) as written
    markup_attributes: str = field(default='', repr=False)     # the same, as render reads them


@dataclass(eq=False)
class List(Node):
    pass


@dataclass(eq=False)
class Item(Node):
    pass


@dataclass(eq=False)
class Strong(Node):
    pass


@dataclass(eq=False)
class Emphasis(Node):
    pass


@dataclass(eq=False)
class Element(Node):
    name: str = ''                  # '' for a bare :: (an anonymous div, a spacer)
    groups: dict = field(default_factory=dict)      # '[]' style, '()' classes and id, '{}' attributes
    value: str = ''                 # the word glued after the groups
    # 'tag' (closed by its ::), 'inline' (div::text::) or 'void' (no children),
    # 'container' (closed at the end of the heading, item, bold or italic it
    # is opened in), 'never' (not closed: no closing tag)
    closed: str = 'tag'
    element: dict = field(default_factory=dict, repr=False)     # what the tag renders from
    tag: Tag | None = field(default=None, repr=False)
    opened_in: Node | None = field(default=None, repr=False)    # its container, None: the document


@dataclass(eq=False)
class Code(Node):
    language: str = ''
    body: str = ''
    index: int = 0


@dataclass(eq=False)
class InlineCode(Node):
    text: str = ''
    index: int = 0


@dataclass(eq=False)
class Math(Node):
    text: str = ''
    display: bool = False
    index: int = 0


@dataclass(eq=False)
class Raw(Node):
    text: str = ''
    raw_kind: str = 'html'          # html, comment, script, style, jinja
    index: int = 0


# ---------------------------------------------------------------------------
# What a tag receives
# ---------------------------------------------------------------------------

@dataclass
class ProcessingContext:
    """What a tag receives as the third argument of its render."""
    media: Callable | None = None   # media(src) -> [(url, mime)], given by the caller
    line_breaks: bool = False


# ---------------------------------------------------------------------------
# The text of the stages, each character with its origin
# ---------------------------------------------------------------------------

class _Text:
    """A text and the origin of each of its characters: an offset of the
    prepared text (>= 0), or -(k + 1) for the k-th event (EVENT_CHAR: the
    opening or the closing of a node, a node without content)."""

    def __init__(self, chars, origins):
        self.chars, self.origins = chars, origins

    def transform(self, pattern, pieces):
        """For each match of `pattern`, the pieces it becomes: (start, end)
        kept from the text, or an event."""
        chars, origins, prev = [], [], 0
        for m in pattern.finditer(self.chars):
            chars.append(self.chars[prev:m.start()])
            origins.extend(self.origins[prev:m.start()])
            for piece in pieces(m):
                if isinstance(piece, tuple):
                    a, b = piece
                    chars.append(self.chars[a:b])
                    origins.extend(self.origins[a:b])
                else:
                    chars.append(EVENT_CHAR)
                    origins.append(-(piece + 1))
            prev = m.end()
        chars.append(self.chars[prev:])
        origins.extend(self.origins[prev:])
        return _Text(''.join(chars), origins)


class _Parser:

    def __init__(self, text, tags):
        self.source = normalize_input(text)
        self.tags = tags
        self.stores = ProtectionStores()
        self.events = []            # (what, node): 'open', 'close', 'leaf'
        self.lines = [0] + [m.end() for m in re.finditer('\n', self.source)]

    # -- positions --------------------------------------------------------

    def _prepared_offsets(self, prepared):
        """The offset in the source of each character of the prepared text."""
        offsets, s, i = [], 0, 0
        while i < len(prepared):
            m = PLACEHOLDER.match(prepared, i)
            if m:
                width = len(self.stores.original(m.group(0)))
                offsets.extend([s] * len(m.group(0)))
                s, i = s + width, m.end()
            else:
                offsets.append(s)
                s, i = s + 1, i + 1
        offsets.append(s)
        return offsets

    def place(self, offset):
        line = bisect.bisect_right(self.lines, offset)
        return line, offset - self.lines[line - 1] + 1

    def source_of(self, origins):
        """The span in the source of characters by their origins."""
        kept = [o for o in origins if o >= 0]
        if not kept:
            return None
        return self.offsets[min(kept)], self.offsets[max(kept) + 1] if max(kept) + 1 < len(self.offsets) \
            else self.offsets[-1]

    def event(self, what, node):
        self.events.append((what, node))
        return len(self.events) - 1

    def _crosses(self, origins):
        """The nodes whose opening the characters hold and not their
        closing, or the other way round (empty: they cross nothing)."""
        opened, closed = set(), set()
        for o in set(origins):
            if o < 0:
                what, node = self.events[-o - 1]
                (opened if what == 'open' else closed if what == 'close' else set()).add(node)
        return opened ^ closed

    # -- the stages ---------------------------------------------------------

    def parse(self):
        url_tags = tuple(sorted(name for name, tag in self.tags.items() if tag.url))
        prepared = process_prepare(self.source, self.stores, url_tags)
        self.offsets = self._prepared_offsets(prepared)
        text = _Text(prepared, list(range(len(prepared))))
        text = self.headings(text)
        text = self.lists(text)
        text = self.inline(text, BOLD, Strong)
        text = self.inline(text, ITALIC, Emphasis)
        text = self.elements(text)
        return self.build(text)

    def headings(self, text):
        def pieces(m):
            level = len(m.group(1))
            class_id = self.stores.restore(m.group(2) or '', 'A').strip()
            node = Heading(level=level, attributes=self.stores.original(m.group(2) or '').strip(),
                           markup_attributes=class_id)
            span = self.source_of(text.origins[m.start():m.end()]) or (0, 0)
            node.span = span
            node.line, node.column = self.place(span[0])
            return [self.event('open', node), (m.start(3), m.end(3)), self.event('close', node)]
        return text.transform(HEADING, pieces)

    def lists(self, text):
        """`* item` lines: a run of them is a list. A deeper level is a list
        inside the item before it (`* a` then `** b`: b's list is in a's
        item); in an item of its own only when there is none to hold it (a
        list that starts at `**`, a jump of two levels). An item stays open
        until the next line at its level, or shallower."""
        chars, origins = [], []

        def gen(event):
            chars.append(EVENT_CHAR)
            origins.append(-(event + 1))

        lines, start = [], 0
        for m in re.finditer('\n', text.chars):
            lines.append((start, m.end()))
            start = m.end()
        if start < len(text.chars):
            lines.append((start, len(text.chars)))
        item = re.compile(r'(\*+) (.*)')
        levels = []
        for a, b in lines:
            m = item.match(text.chars, a, b)
            levels.append(len(m.group(1)) if m else 0)
        open_lists = []                 # one per level: [List, the item open in it, or None]
        for k, (a, b) in enumerate(lines):
            line_level = levels[k]
            if line_level:
                if len(open_lists) == line_level and open_lists[-1][1] is not None:
                    gen(self.event('close', open_lists[-1][1]))     # the item before, at this level
                    open_lists[-1][1] = None
                while len(open_lists) < line_level:
                    if open_lists and open_lists[-1][1] is None:     # nothing to hold the deeper list
                        wrapper = Item()
                        gen(self.event('open', wrapper))
                        open_lists[-1][1] = wrapper
                    lst = List()
                    gen(self.event('open', lst))
                    open_lists.append([lst, None])
                node = Item()
                m = item.match(text.chars, a, b)
                gen(self.event('open', node))
                open_lists[-1][1] = node
                span = self.source_of(text.origins[a:b])
                if span:
                    node.span = span
                    node.line, node.column = self.place(span[0])
                end = m.end(2)
                chars.append(text.chars[m.start(2):end])
                origins.extend(text.origins[m.start(2):end])
                if end < len(text.chars) and text.chars[end] == '\n':
                    chars.append('\n')
                    origins.append(text.origins[end])
                else:                   # the last line: its line break is written, as content
                    brk = Text(value='\n', raw='\n')
                    if span:            # where the line ends
                        brk.span = (span[1], span[1])
                        brk.line, brk.column = self.place(span[1])
                    gen(self.event('leaf', brk))
            else:
                chars.append(text.chars[a:b])
                origins.extend(text.origins[a:b])
            next_level = levels[k + 1] if k + 1 < len(lines) else 0
            while len(open_lists) > next_level:      # the deeper lists end here, with their item
                lst, open_item = open_lists.pop()
                if open_item is not None:
                    gen(self.event('close', open_item))
                gen(self.event('close', lst))
        return _Text(''.join(chars), origins)

    def inline(self, text, pattern, kind):
        def pieces(m):
            node = kind()
            span = self.source_of(text.origins[m.start():m.end()])
            crossed = self._crosses(text.origins[m.start():m.end()])
            if crossed:                 # an italic across a bold
                marker = m.group(0)[:2]
                _warn(f'{marker}...{marker} would cross a {_KINDS[type(next(iter(crossed)))]}: '
                      f'it is left as text (near {self.source[span[0]:span[1]]!r})',
                      self.place(span[0]) if span else None)
                return [(m.start(), m.end())]
            if span:
                node.span = span
                node.line, node.column = self.place(span[0])
            return [self.event('open', node), (m.start(1), m.end(1)), self.event('close', node)]
        return text.transform(pattern, pieces)

    def elements(self, text):
        """The `::` elements, decided on the text the stages wrote, recorded
        as events: an element's source becomes one event, and its `::`
        another. The open elements are kept with the container each is
        opened in (a heading, a list item, a bold, an italic, or the
        document): a `::` closes the last one when it is in that container,
        and an element is closed at the end of its container."""
        chars, origins = [], []
        prev, last_tag_end = 0, -1
        flat = text.chars               # the text, each node read by a stage one EVENT_CHAR
        containers, closes = self._containers(text)
        self.open, self.closed_early, self.next_close = [], [], 0
        resolve = lambda s: self.stores.restore(self.stores.restore(s, 'A'), 'U')
        for m in TAG_MARKER.finditer(flat):
            if m.start() < prev:
                continue
            line, column = self._place_of(text, m.start())
            try:
                element = extract_bracket_elements(flat, m.end())
            except LHTMLParseError as e:
                found = _TAG_NAME_BEFORE.search(flat, max(0, m.start() - _MAX_TAG_NAME), m.start())
                name = len(found.group()) if found else 0
                _warn(f'{e} near {self._quote(text, m.start() - name, m.end() + 30)!r}',
                      (line, column - name if column else None))
                continue
            tag = element['tag']
            tag_start = m.start() - len(tag)
            if tag_start < prev:
                tag, tag_start = '', m.start()
                element.update({'tag': '', 'index_start': tag_start})
            if not _is_tag_boundary(flat, tag_start, tag, last_tag_end):
                continue
            if not tag and not _adjust_bare_tag(flat, m, element):
                continue
            element['line'] = line
            element['column'] = column - len(tag) if column else None
            context = resolve(self._shown(text, tag_start, element['index_end']))
            element['context'] = _context(context, 0, len(context))
            if any(EVENT_CHAR in element[key] for key in ('text', '[]', '()', '{}')):
                self._show_groups(text, m.end(), element)
            for key in ('text', '[]', '()', '{}'):
                element[key] = resolve(element[key])
            self._end_containers(closes, tag_start)
            crossing = self._crosses(text.origins[tag_start:element['index_end']])
            if crossing:                # its source as written, not the markup the stages wrote
                span = self.source_of(text.origins[tag_start:element['index_end']])
                crossing = _context(self.source[span[0]:span[1]], 0, span[1] - span[0])
            what = self._decide(element, containers[tag_start], crossing)
            if what is None:            # not a tag: its text stays, and is not read again
                chars.append(text.chars[prev:element['index_end']])
                origins.extend(text.origins[prev:element['index_end']])
                prev = element['index_end']
                continue
            chars.append(text.chars[prev:tag_start])
            origins.extend(text.origins[prev:tag_start])
            kind, node = what
            span = self.source_of(text.origins[tag_start:element['index_end']])
            if kind == 'close':         # the element ends with its ::
                if span:
                    node.span = (node.span[0], span[1])
            else:
                if span:
                    node.span = span
                node.line, node.column = element['line'], element['column']
            event = self.event(kind, node)
            chars.append(EVENT_CHAR)
            origins.append(-(event + 1))
            prev = last_tag_end = element['index_end']
        self._end_containers(closes, len(flat) + 1)
        for node in self.open:
            _warn(f"{_label(node)} is never closed (near {node.element['context']!r})", node.element)
        chars.append(text.chars[prev:])
        origins.extend(text.origins[prev:])
        return _Text(''.join(chars), origins)

    def _shown(self, text, start, end):
        """The text between two positions with the markup of its nodes,
        as the text passes wrote it ('<strong>'): what an element holds in
        its groups (a link label), what a message quotes."""
        start = max(0, start)
        if EVENT_CHAR not in text.chars[start:end]:
            return text.chars[start:end]
        parts = []
        for ch, origin in zip(text.chars[start:end], text.origins[start:end]):
            if ch != EVENT_CHAR or origin >= 0:
                parts.append(ch)
                continue
            what, node = self.events[-origin - 1]
            if what == 'leaf':
                parts.append(node.raw)
            else:
                parts.append(_MARKUP[type(node)](node)[what == 'close'])
        return ''.join(parts)

    def _quote(self, text, start, end):
        """What a message quotes of the text between two positions: its
        source as written, on one line."""
        span = self.source_of(text.origins[max(0, start):end])
        return _context(self.source[span[0]:span[1]], 0, span[1] - span[0]) if span else ''

    def _show_groups(self, text, after, element):
        """The groups (and the text of a stray element) of an element whose
        source holds nodes: with their markup (extract_bracket_elements
        joins the groups of a kind with a space)."""
        if element['()'] == element['[]'] == element['{}'] == '' and element['groups'] \
                and EVENT_CHAR in element['text']:    # stray: all of it is its text
            element['text'] = self._shown(text, after, element['index_end'])
            return
        for kind in ('[]', '()', '{}'):
            element[kind] = ' '.join(self._shown(text, a, b) for k, a, b in element['groups'] if k == kind)

    def _containers(self, text):
        """The innermost container open at each position of the text (None:
        the document), and where each container closes: [(position, node)]."""
        at, stack, seen, closes = [], [None], set(), []
        for i, o in enumerate(text.origins):
            if o < 0 and o not in seen:
                seen.add(o)
                what, node = self.events[-o - 1]
                if what == 'open':
                    if isinstance(node, List) and isinstance(stack[-1], Item):
                        # the text of an item is its line: an element left open
                        # there ends where its nested list begins
                        closes.append((i, stack[-1]))
                    stack.append(node)
                elif what == 'close':
                    stack.remove(node)  # the last one: the containers nest (inline refuses a crossing)
                    closes.append((i, node))
            at.append(stack[-1])
        at.append(stack[-1])
        return at, closes

    def _end_containers(self, closes, position):
        """The elements opened in the containers that close before
        `position`: closed there, their `::` elsewhere or missing."""
        while self.next_close < len(closes) and closes[self.next_close][0] < position:
            container = closes[self.next_close][1]
            self.next_close += 1
            while self.open and self.open[-1].opened_in is container:
                node = self.open.pop()
                _warn(f'{_label(node)} is closed at the end of the {_KINDS[type(container)]} it is '
                      f"opened in: its :: is elsewhere, or missing (near {node.element['context']!r})",
                      node.element)
                self.closed_early.append(node)

    def _place_of(self, text, position):
        origin = text.origins[position]
        if origin < 0:
            return None, None
        return self.place(self.offsets[origin])

    def _decide(self, element, container, crossing):
        """(event, node) of an element; None when it is not a tag (its
        source stays)."""
        tag = element['tag']
        if element['[]'] == '-' and tag != 'link':
            _refuse_explicit_closing(element)
        if tag and tag not in self.tags:
            return None
        if element.get('stray'):
            _warn(f'{tag}:: has a closing bracket without its opening one: its groups are left as text '
                  f"(near {element.get('context', '')!r})", element)
        if crossing:                    # a label across the end of a heading, an item, a bold
            _warn(f'{tag}:: is left as text: its text would cross the end of a heading, list item, '
                  f'bold or italic (near {crossing!r})', element)
            return None
        if tag:
            return self._open(element, self.tags[tag], tag, container)
        if check_is_closing_tag(element):
            return self._close_tag(element, container)
        if element['text'] == 'nl':
            return 'leaf', Element(groups=self._written(element), value='nl',
                                   closed='void', element=element, tag=SPACER, opened_in=container)
        if element['[]'] or element['()'] or element['{}'] or element['text']:
            return self._open(element, self.tags['div'], '', container)    # an anonymous div
        return None

    def _written(self, element):
        """The groups of an element as written: the zones they hold (Jinja,
        mathematics, inline code) as written, the bold and italic of a link
        label as HTML (the stages read them before the element). The element
        keeps the placeholders of the zones for its tag, as the text passes
        gave them."""
        return {k: self.stores.original(element[k]) for k in ('[]', '()', '{}')}

    def _open(self, element, tag, name, container):
        try:
            holds = tag.holds(element)
        except LHTMLError:
            raise
        except Exception as e:
            raise _tag_error(f'{name}::', 'container', e, element) from e
        closed = 'tag' if holds else 'inline' if element['text'].endswith('::') else 'void'
        node = Element(name=name, groups=self._written(element),
                       value=self.stores.original(element['text']), closed=closed, element=element, tag=tag,
                       opened_in=container)
        if holds:
            self.open.append(node)
            return 'open', node
        return 'leaf', node

    def _close_tag(self, element, container):
        """A `::`: it closes the last open element if they are in the same
        container; otherwise it closes nothing, and stays as text."""
        top = self.open[-1] if self.open else None
        if top is not None and top.opened_in is container:
            return 'close', self.open.pop()
        early = self.closed_early[-1] if self.closed_early else None
        if early is not None and (top is None or early.element['index_start'] > top.element['index_start']):
            self.closed_early.pop()
            _warn(f'this :: closes nothing: {_label(early)} was closed at the end of the '
                  f"{_KINDS[type(early.opened_in)]} it is opened in (near {early.element['context']!r})",
                  element)
        elif top is not None:
            _warn(f'this :: closes nothing: it is inside a {_KINDS.get(type(container), "container")} '
                  f"that {_label(top)} is not in (near {top.element['context']!r})", element)
        else:
            _warn(f"Closing tag :: has no matching opening tag (near {element.get('context', '')!r})",
                  element)
        return None

    # -- the tree ---------------------------------------------------------------

    def build(self, text):
        document = Document(span=(0, len(self.source)), stores=self.stores)
        stack = [document]
        buffer, buffer_origins = [], []
        done = set()

        def flush():
            if buffer:
                self._text_nodes(''.join(buffer), buffer_origins, stack[-1])
                buffer.clear()
                buffer_origins.clear()

        for ch, origin in zip(text.chars, text.origins):
            if origin >= 0:
                buffer.append(ch)
                buffer_origins.append(origin)
                continue
            event = -origin - 1
            if event in done:           # the other characters of the same markup
                continue
            done.add(event)
            flush()
            what, node = self.events[event]
            if what == 'open':
                if isinstance(node, List):      # the elements open in the text of its item end here
                    k = len(stack) - 1
                    while isinstance(stack[k], Element):
                        k -= 1
                    if isinstance(stack[k], Item):
                        while len(stack) > k + 1:
                            stack.pop().closed = 'container'
                stack[-1].children.append(node)
                stack.append(node)
            elif what == 'leaf':
                stack[-1].children.append(node)
            else:                       # the elements still open in it end with it (warned)
                while stack[-1] is not node:
                    stack.pop().closed = 'container'
                stack.pop()
        flush()
        for node in stack[1:]:          # elements never closed: no closing tag
            node.closed = 'never'
        self._spans(document)
        return document

    def _spans(self, document):
        """A node that has no source of its own (a list, a wrapper item)
        spans its children; an element spans them too when it holds them."""
        for node in reversed(list(document.walk())):        # the children first
            located = [child.span for child in node.children if child.line is not None]
            if not located or node is document:
                continue
            start, end = min(a for a, _ in located), max(b for _, b in located)
            if node.line is None:
                node.span = (start, end)
                node.line, node.column = self.place(start)
            else:
                node.span = (min(node.span[0], start), max(node.span[1], end))

    def _text_nodes(self, raw, origins, parent):
        """Text, and the opaque zones its placeholders hold (a URL or a
        group hidden in a text is text: one node with the text around it)."""
        nodes, position = [], 0
        for m in PLACEHOLDER.finditer(raw):
            if m.start() > position:
                nodes.append(self._text(raw[position:m.start()], origins[position:m.start()]))
            nodes.append(self._zone(m, origins[m.start():m.end()]))
            position = m.end()
        if position < len(raw):
            nodes.append(self._text(raw[position:], origins[position:]))
        for node in nodes:
            last = parent.children[-1] if parent.children else None
            if isinstance(node, Text) and isinstance(last, Text) and last.span[1] == node.span[0]:
                last.value += node.value
                last.raw += node.raw
                last.span = (last.span[0], node.span[1])
            else:
                parent.children.append(node)

    def _located(self, node, origins):
        span = self.source_of(origins)
        if span:
            node.span = span
            node.line, node.column = self.place(span[0])
        return node

    def _text(self, raw, origins):
        return self._located(Text(value=self.stores.original(raw), raw=raw), origins)

    def _zone(self, m, origins):
        kind, index = m.group(1), int(m.group(2))
        original = self.stores.original(m.group(0))
        if kind == 'C':
            header, body = self.stores.C[index]
            node = Code(language=_code_language(header), body=body, index=index)
        elif kind == 'I':
            node = InlineCode(text=original[1:-1], index=index)
        elif kind == 'R' and original.startswith(('\\(', '\\[')):
            node = Math(text=original, display=original.startswith('\\['), index=index)
        elif kind == 'R':
            raw_kind = ('comment' if original.startswith(('<!--', '{#')) else
                        'jinja' if original.startswith(('{{', '{%')) else
                        'script' if original[:7].lower() == '<script' else
                        'style' if original[:6].lower() == '<style' else 'html')
            node = Raw(text=original, raw_kind=raw_kind, index=index)
        else:                           # a URL or a group of an element that is not one: text
            return self._located(Text(value=original, raw=m.group(0)), origins)
        return self._located(node, origins)


# ---------------------------------------------------------------------------
# The public functions
# ---------------------------------------------------------------------------

_KINDS = {Heading: 'heading', List: 'list', Item: 'list item', Strong: 'bold', Emphasis: 'italic'}


def _label(node):
    return f'{node.name}::'


def _tag_error(label, what, error, element):
    return LHTMLError(f'{label} its {what} raised {type(error).__name__}: {error} '
                      f"(near {element.get('context', label)!r})", element.get('line'), element.get('column'))


def _registry(tags, macros):
    """The built-in TAGS, the macros, then the tags given (which win)."""
    if macros is not None and not isinstance(macros, Mapping):
        raise TypeError(f'macros: expected a mapping of definitions, got {type(macros).__name__} '
                        f'(the macros of files: lhtml.load_macros(path or [paths]))')
    registry = registry_with_macros(macros) if macros else dict(TAGS)
    for name, tag in (tags or {}).items():
        if not isinstance(tag, Tag):
            raise TypeError(f'tag {name!r}: expected an lhtml.Tag(render, container), '
                            f'got {type(tag).__name__}')
        if not isinstance(name, str) or not NAME_RE.match(name):
            raise ValueError(f'invalid tag name {name!r} (a letter, then letters, digits, _ or -)')
        if name in NOT_ELEMENTS:
            raise ValueError(f'{name}:: is LHTML syntax, not an element: it cannot be a tag')
        registry[name] = tag
    return registry


def _given_offsets(given, normalized):
    """Offsets in the normalized text -> offsets in the text given to parse
    (normalize_input removes a BOM and the \\r of \\r\\n)."""
    bom = 1 if given.startswith('\ufeff') else 0
    if not bom and len(given) == len(normalized):
        return None
    removed = [m.start() - k for k, m in enumerate(re.finditer('\r\n', given[bom:]))]
    return lambda o: o + bom + bisect.bisect_left(removed, o)


def parse(text, *, macros=None, tags=None):
    """The document tree of an LHTML text. `macros`: the definitions of the
    macros, a mapping (lhtml.load_macros reads them from files); `tags`:
    {name: Tag}, added to the built-in TAGS and the macros (a tag given
    wins). Reads no file. The warnings are emitted, and kept in
    document.problems, in source order."""
    registry = _registry(tags, macros)
    caught = []
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            parser = _Parser(text, registry)
            document = parser.parse()
    finally:                            # emitted, an error raised or not
        caught = sorted(caught, key=lambda w: (getattr(w.message, 'line', None) is None,
                                               getattr(w.message, 'line', None) or 0,
                                               getattr(w.message, 'column', None) or 0))
        for w in caught:
            warnings.warn_explicit(w.message, w.category, w.filename, w.lineno)
    given = _given_offsets(text, parser.source)
    if given:
        for node in document.walk():
            node.span = (given(node.span[0]), given(node.span[1]))
    document.span = (0, len(text))
    document.problems = [w.message for w in caught]
    return document


_MARKUP = {
    Heading: lambda node: (f'<h{node.level}'
                           + (export_html_element_class_and_id(node.markup_attributes)
                              if node.markup_attributes else '')
                           + '>', f'</h{node.level}>\n'),
    List: lambda node: ('<ul>\n', '</ul>\n'),
    Item: lambda node: ('<li>\n', '</li>\n'),
    Strong: lambda node: ('<strong>', '</strong>'),
    Emphasis: lambda node: ('<em>', '</em>'),
}
_STORE = {Code: 'C', InlineCode: 'I', Math: 'R', Raw: 'R'}


def _node_html(node, children, context):
    """The HTML of a node around the HTML of its children."""
    markup = _MARKUP.get(type(node))
    if markup is not None:
        opening, closing = markup(node)
        return opening + children + closing
    if not isinstance(node, Element):
        return children
    element = {**node.element, 'closed': node.closed != 'never'}
    try:
        html = node.tag.render(element, children, context)
    except LHTMLError:
        raise
    except Exception as e:
        raise _tag_error(_label(node), 'render', e, node.element) from e
    if not isinstance(html, str):
        raise LHTMLError(f'{_label(node)} its render returned {type(html).__name__}, not a str '
                         f"(near {node.element.get('context')!r})", node.line, node.column)
    return html


def _render_tree(root, context):
    """The HTML of a node, its children first (no recursion: a document may
    nest deeper than Python's recursion limit)."""
    stack = [(root, iter(root.children), [])]
    while True:
        node, children, parts = stack[-1]
        child = next(children, None)
        if child is None:
            stack.pop()
            html = _node_html(node, ''.join(parts), context)
            if not stack:
                return html
            stack[-1][2].append(html)
        elif isinstance(child, Text):
            parts.append(child.raw)
        elif type(child) in _STORE:
            parts.append(f'\x00{_STORE[type(child)]}{child.index}\x00')
        else:
            stack.append((child, iter(child.children), []))


def _tokens(document, context):
    """The HTML of the nodes as tokens, in order: (html, kind), kind 'text',
    'leaf' or 'markup' (process.line_breaks). Each tag is rendered once,
    with its children, as without line-breaks; where its HTML holds its
    children once and as given, it is split around them (its opening, the
    tokens of its children, its closing). A tag that transforms or repeats
    its children is one token: its HTML as it wrote it."""
    out = []
    stack = [(document, iter(document.children), 0)]      # (node, its children, where its tokens start)
    while stack:
        node, children, start = stack[-1]
        child = next(children, None)
        if child is not None:
            if isinstance(child, Text):
                out.append((child.raw, 'text'))
            elif type(child) in _STORE:
                out.append((f'\x00{_STORE[type(child)]}{child.index}\x00', 'leaf'))
            else:
                out.append(None)        # its opening, once its children are written
                stack.append((child, iter(child.children), len(out)))
            continue
        stack.pop()
        if node is document:
            return out
        if type(node) in _MARKUP:
            opening, closing = _MARKUP[type(node)](node)
            out[start - 1] = (opening, 'markup')
            out.append((closing, 'markup'))
            continue
        children_html = ''.join(html for html, _ in out[start:])
        html = _node_html(node, children_html, context)
        at = html.find(children_html) if children_html else -1
        if at >= 0 and html.count(children_html) == 1:
            out[start - 1] = (html[:at], 'markup')
            out.append((html[at + len(children_html):], 'markup'))
        else:
            del out[start:]
            out[start - 1] = (html, 'markup')


def render(document, *, line_breaks=False, media=None):
    """The HTML of a document tree. `line_breaks`: the line breaks of the
    source are rendered as <br>; `media`: the resolver of the sources of a
    video, media(src) -> [(url, mime type)] (none: the source as written)."""
    if media is not None and not callable(media):
        raise TypeError(f'"media" must be callable, got {type(media).__name__}')
    context = ProcessingContext(media, bool(line_breaks))
    stores = document.stores
    if context.line_breaks:
        text = _with_line_breaks(_tokens(document, context), stores)
    else:
        text = _render_tree(document, context)
    text = stores.restore(text, 'I', render_inline_code)
    text = process_unprotect(text, stores)
    text = stores.restore(text, 'C', render_code_block)
    return text
