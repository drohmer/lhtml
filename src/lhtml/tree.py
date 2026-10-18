"""The document tree of LHTML: parse, then render (lhtml.run is both).

    document = parse(text, macros=None, tags=None)
    html     = render(document, line_breaks=False, media=None)    (render.py)

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
passes of LHTML 2 and of the 3.0 development versions, which wrote '<h1>',
'<strong>' into the text instead (the tree replaced them on 2026-10-17 with the same HTML on the
tests, a corpus of five projects and 80 000 fuzzed documents). Each
character keeps its origin, the source or an event; the tree is built from
the events. A tag builds the nodes of its element (export_html.Tag), the
label of a link is its children, and the placeholders of the zones are
gone from the tree: `render` writes the HTML from the fields of the nodes
alone (nodes.py).

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
import os
import re
import sys
import warnings
from collections.abc import Mapping

from . import attributes
from .errors import PROBLEMS, LHTMLError, LHTMLParseError, LHTMLWarning, quote, suggestion, warn
from .attributes import class_and_id
from .tags import SPACER, TAGS, Tag, node_list
from .macros import NAME_RE, NOT_ELEMENTS, registry_with_macros
from .nodes import (
    Code, Document, Element, Emphasis, Heading, InlineCode, Item, List, Math, Node, Raw, Strong, Text, Written,
)
from .patterns import (
    BOLD, CODE_BLOCK, EVENT_CHAR, HEADING, ITALIC, PLACEHOLDER, TAG_MARKER,
)
from .process import ProtectionStores, code_language, normalize_input, process_prepare
from .tag_parser import (
    adjust_bare_tag, extract_bracket_elements, is_closing_tag, is_tag_boundary, refuse_explicit_closing,
    tag_name_before,
)


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
        self.events = []            # (what, node): 'open', 'close', 'leaf' (a list of nodes)
        self.parsed = {}            # an element -> (its element dict, the container it is opened in)
        self.built = set()          # the nodes the tags built: text after them is not theirs
        self.lines = [0] + [m.end() for m in re.finditer('\n', self.source)]
        self.offsets = []           # the offset in the source of each origin (_offsets, _placed)
        self.open, self.closed_early, self.next_close = [], [], 0   # the :: elements (elements)
        self._glued = None          # the word:: that may be meant as a closing :: (_glued_close)
        self.prepared = ''          # the source, its zones LHTML does not read hidden (parse)

    # -- positions --------------------------------------------------------

    def _offsets(self, text, start=0):
        """The offset in the source of each character of a text whose source
        starts at `start`, and the offset after it: a placeholder's
        characters are all where what it hides starts."""
        offsets, s, prev = [], start, 0
        for m in PLACEHOLDER.finditer(text):
            offsets.extend(range(s, s + m.start() - prev))
            s += m.start() - prev
            offsets.extend([s] * len(m.group(0)))
            s += len(self.stores.original(m.group(0)))
            prev = m.end()
        offsets.extend(range(s, s + len(text) - prev + 1))
        return offsets

    def place(self, offset):
        line = bisect.bisect_right(self.lines, offset)
        return line, offset - self.lines[line - 1] + 1

    def source_of(self, origins):
        """The span in the source of characters by their origins (in the
        order of the source: from the first to the last that is no event)."""
        first = next((o for o in origins if o >= 0), None)
        if first is None:
            return None
        last = next(o for o in reversed(origins) if o >= 0)
        return self.offsets[first], self.offsets[last + 1]

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
                if what != 'leaf':
                    (opened if what == 'open' else closed).add(node)
        return opened ^ closed

    # -- the stages ---------------------------------------------------------

    def parse(self):
        url_tags = tuple(sorted(name for name, tag in self.tags.items() if tag.url))
        prepared = process_prepare(self.source, self.stores, url_tags)
        self.offsets = self._offsets(prepared)
        self.prepared = prepared
        text = _Text(prepared, list(range(len(prepared))))
        text = self.headings(text)
        text = self.lists(text)
        text = self.inline(text, BOLD, Strong)
        text = self.inline(text, ITALIC, Emphasis)
        self._across_lines(text)
        text = self.elements(text)
        return self.build(text)

    def headings(self, text):
        for m in _HEADING_GROUP.finditer(text.chars):      # =[style] T, ={id="x"} T: text
            warn(f'{self._quote(text, m.start(), m.end())}: a heading takes (.class #id) only, it is '
                 f'left as text', self._place_of(text, m.start()))

        def pieces(m):
            level = len(m.group(1))
            written = self.stores.original(m.group(2) or '').strip()
            node = Heading(level=level, attributes=class_and_id(written), written=written)
            span = self.source_of(text.origins[m.start():m.end()]) or (0, 0)
            node.span = span
            node.line, node.column = self.place(span[0])
            return [self.event('open', node), (m.start(3), m.end(3)), self.event('close', node)]
        return text.transform(HEADING, pieces)

    def _across_lines(self, text):
        """A ** or __ that opens on a line and one that closes on a later
        line of the paragraph: a bold or an italic across lines, which is
        none (each is within its line). Warned at the first, once."""
        chars = text.chars
        for mark in ('**', '__'):
            opener, line, counted = None, 0, 0
            for m in _MARK.finditer(chars):
                line += chars.count('\n', counted, m.start())
                counted = m.start()
                if m.group(0) != mark:          # a blank line: the paragraph ends
                    opener = None
                    continue
                before, after = chars[m.start() - 1:m.start()], chars[m.end():m.end() + 1]
                closes = before.strip() and not after.strip(' \t\n.,;:!?)')
                if opener is not None and closes:
                    if line > opener[1]:
                        kind = 'bold' if mark == '**' else 'italic'
                        warn(f'{mark}...{mark} across lines is no {kind} (each is within its line): it is '
                             f'left as text (near {self._quote(text, opener[0], opener[0] + 30)!r})',
                             self._place_of(text, opener[0]))
                    opener = None
                elif (not before.strip() or before == '(') and after.strip():
                    opener = (m.start(), line)

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
                    brk = Text(value='\n')
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
                warn(f'{marker}...{marker} would cross a {_KINDS[type(next(iter(crossed)))]}: '
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
        original = self.stores.original
        for m in TAG_MARKER.finditer(flat):
            if m.start() < prev:
                continue
            tag = tag_name_before(flat, m.start())
            tag_start = m.start() - len(tag)
            if tag_start < prev:
                tag, tag_start = '', m.start()
            # a :: glued to a word is no tag: decided before its element is read (a::a::a...: linear)
            if not is_tag_boundary(flat, tag_start, tag, last_tag_end):
                continue
            line, column = self._place_of(text, m.start())
            try:
                element = extract_bracket_elements(flat, m.end())
            except LHTMLParseError as e:
                warn(f'{tag}:: {e}: it is left as text (near {self._quote(text, tag_start, m.end() + 30)!r})',
                      (line, column - len(tag) if column else None))
                continue
            element.tag, element.start = tag, tag_start
            if not tag and not adjust_bare_tag(flat, m, element):
                continue
            element.line = line
            element.column = column - len(tag) if column else None
            element.context = self._quote(text, tag_start, element.end)
            element.label = None
            if element.stray:    # all of it is its text
                if EVENT_CHAR in flat[m.end():element.end]:
                    warn(f'{tag}:: has a closing bracket without its opening one: it is left as text '
                          f"(near {element.context!r})", element)
                    chars.append(text.chars[prev:element.end])
                    origins.extend(text.origins[prev:element.end])
                    prev = element.end
                    continue
            element.text = original(element.text)
            element.clear_groups()              # each group as written, then joined
            for kind, a, b in (() if element.stray else element.groups):     # stray: all of it is text
                written = flat[a:b]
                if EVENT_CHAR in written:       # across nodes (a bold, a list): its source
                    written = self._source(text, a - 1, b + 1)[1:-1]
                element.add_group(kind, original(written))
            if tag in self.tags and attributes.unclosed(element.braces):
                warn(f"{tag}:: a value of its {{...}} has no closing quote: it is written so "
                      f"(near {element.context!r})", element)
            element.inline = element.text.endswith('::')
            if element.inline:
                element.text = element.text[:-2]
            self._end_containers(closes, tag_start)
            crossing = self._crosses(text.origins[tag_start:element.end])
            if crossing:                # its source as written, not the markup the stages wrote
                span = self.source_of(text.origins[tag_start:element.end])
                crossing = quote(self.source[span[0]:span[1]], 0, span[1] - span[0])
            if tag == 'link' and not crossing and not element.stray:     # its label: nodes
                label = [(a, b) for kind, a, b in element.groups if kind == '[]']
                element.label = self._label_nodes(text, label)
                element.brackets = ' '.join(self._source(text, a - 1, b + 1)[1:-1] for a, b in label)
            what = self._decide(element, containers[tag_start], crossing)
            if what is None:            # not a tag: its text stays, and is not read again
                chars.append(text.chars[prev:element.end])
                origins.extend(text.origins[prev:element.end])
                prev = element.end
                continue
            chars.append(text.chars[prev:tag_start])
            origins.extend(text.origins[prev:tag_start])
            kind, node = what
            span = self.source_of(text.origins[tag_start:element.end])
            if kind == 'close':         # the element ends with its ::
                if span:
                    node.span = (node.span[0], span[1])
            else:                       # the nodes its tag built, where it is
                for built in (node if kind == 'leaf' else [node]):
                    for n in built.walk():
                        self.built.add(n)
                        if n.line is None:
                            n.span = span or n.span
                            n.line, n.column = element.line, element.column
            event = self.event(kind, node)
            chars.append(EVENT_CHAR)
            origins.append(-(event + 1))
            prev = last_tag_end = element.end
        self._end_containers(closes, len(flat) + 1)
        for node in self.open:
            element = self.parsed[node][0]
            if not element.warned:
                warn(f"{_label(node)} is never closed{self._glued_close(node)} "
                      f"(near {element.context!r})", element)
        chars.append(text.chars[prev:])
        origins.extend(text.origins[prev:])
        return _Text(''.join(chars), origins)

    def _source(self, text, start, end):
        """The source as written of the text between two positions."""
        span = self.source_of(text.origins[start:end])
        return self.source[span[0]:span[1]] if span else ''

    def _label_nodes(self, text, ranges):
        """The nodes of the label of a link (its [...] groups, joined by a
        space): its text, bold, italic, zones."""
        root = Node()
        for k, (start, end) in enumerate(ranges):
            if k:                       # the groups joined by a space, where the first one closes
                joint = self.source_of(text.origins[ranges[k - 1][1]:ranges[k - 1][1] + 1])
                space = Text(value=' ')
                if joint:
                    space.span = (joint[0], joint[0])
                    space.line, space.column = self.place(joint[0])
                root.children.append(space)
            self._replay(text.chars[start:end], text.origins[start:end], root)
        return root.children

    def _quote(self, text, start, end):
        """What a message quotes of the text between two positions: its
        source as written, on one line."""
        span = self.source_of(text.origins[max(0, start):end])
        return quote(self.source[span[0]:span[1]], 0, span[1] - span[0]) if span else ''

    def _containers(self, text):
        """The innermost container open at each position of the text (None:
        the document), and where each container closes: [(position, node)]."""
        at, stack, closes = [], [None], []
        for i, o in enumerate(text.origins):
            if o < 0:                   # an event: one character
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
            while self.open and self.parsed[self.open[-1]][1] is container:
                node = self.open.pop()
                element = self.parsed[node][0]
                if not element.warned:
                    warn(f'{_label(node)} is closed at the end of the {_KINDS[type(container)]} it is '
                          f"opened in: its :: is elsewhere, or missing (near {element.context!r})",
                          element)
                self.closed_early.append(node)

    def _place_of(self, text, position):
        origin = text.origins[position]
        if origin < 0:
            return None, None
        return self.place(self.offsets[origin])

    def _decide(self, element, container, crossing):
        """(event, node) of an element; None when it is not a tag (its
        source stays)."""
        tag = element.tag
        if element.brackets == '-' and tag != 'link':
            refuse_explicit_closing(element)
            if self.open:               # the element it was meant to close: warned with it
                self.parsed[self.open[-1]][0].warned = True
        if tag and tag not in self.tags:
            self._not_a_tag(element)
            return None
        if element.stray:
            warn(f'{tag}:: has a closing bracket without its opening one: its groups are left as text '
                  f"(near {element.context!r})", element)
        if crossing:                    # a label across the end of a heading, an item, a bold
            warn(f'{tag}:: is left as text: its text would cross the end of a heading, list item, '
                  f'bold or italic (near {crossing!r})', element)
            return None
        if tag:
            return self._open(element, self.tags[tag], tag, container)
        if is_closing_tag(element):
            return self._close_tag(element, container)
        if element.text == 'nl':
            return self._open(element, SPACER, '', container)
        if element.brackets or element.parentheses or element.braces or element.text or element.groups:
            return self._open(element, self.tags['div'], '', container)    # an anonymous div
        return None

    def _open(self, element, tag, name, container):
        """The nodes the tag builds: ('open', its element) when it holds
        what follows, else ('leaf', [nodes])."""
        given = Written(tag=element.tag, text=element.text, inline=element.inline,
                        parentheses=element.parentheses, brackets=element.brackets, braces=element.braces,
                        label=None if element.label is None else tuple(element.label),
                        line=element.line, column=element.column, context=element.context)
        holds = self._call(name, 'container', element, tag.holds, given)
        built = self._call(name, 'build', element, lambda w: node_list(tag.build(w)), given)
        if holds and (len(built) != 1 or not isinstance(built[0], Element)):
            raise _tag_error(f'{name}::', 'build', TypeError('a container builds one Element'), element)
        for node in built:
            if isinstance(node, Element):
                node.written = given
        if holds:
            self.parsed[built[0]] = (element, container)
            self.open.append(built[0])
            return 'open', built[0]
        return 'leaf', built

    def _not_a_tag(self, element):
        """A name that is no tag stays as text (std::vector): warned when a
        group follows its :: at once (code::[python] never closed, bx::(.c)
        for box::(.c))."""
        tag, groups = element.tag, element.groups
        after = element.start + len(tag) + 2     # just after its ::
        if element.warned or not groups or groups[0][1] != after + 1:
            return
        if tag == 'code' and groups[0][0] == '[]':
            warn(f"code::[{element.brackets}] is never closed (its code::[-] is missing): what follows "
                  f"is read as LHTML", element)
        else:
            warn(f'{tag}:: is no tag, it is left as text{suggestion(tag, self.tags)} '
                  f"(near {element.context!r})", element)

    def _glued_close(self, node):
        """'; ... is no closing ::' when a word:: after the element was
        meant to close it (span::[c] text word::)."""
        if self._glued is None:     # read once: many elements may never be closed
            # in the text LHTML reads: a word:: in a code block or a comment is no closing meant
            self._glued = [(self.offsets[m.start()], m.group(1)) for m in _GLUED_CLOSE.finditer(self.prepared)
                           if m.group(1) not in self.tags]
        k = bisect.bisect_left(self._glued, (node.span[0], ''))
        if k == len(self._glued):
            return ''
        word = self._glued[k][1]
        return f"; {word}:: is no closing ::, write '{word} ::'"

    def _call(self, name, what, element, function, given):
        """A function of a tag: an exception it raises is an LHTMLError
        naming the tag and its place (the exception as its cause)."""
        try:
            return function(given)
        except LHTMLError:
            raise
        except Exception as e:
            raise _tag_error(f'{name}::', what, e, element) from e

    def _close_tag(self, element, container):
        """A `::`: it closes the last open element if they are in the same
        container; otherwise it closes nothing, and stays as text."""
        top = self.open[-1] if self.open else None
        if top is not None and self.parsed[top][1] is container:
            return 'close', self.open.pop()
        early = self.closed_early[-1] if self.closed_early else None
        start = lambda node: self.parsed[node][0].start
        if early is not None and (top is None or start(early) > start(top)):
            self.closed_early.pop()
            if self.parsed[early][0].warned:     # the :: of an element warned already
                return None
            warn(f'this :: closes nothing: {_label(early)} was closed at the end of the '
                  f"{_KINDS[type(self.parsed[early][1])]} it is opened in "
                  f"(near {self.parsed[early][0].context!r})", element)
        elif top is not None:
            warn(f'this :: closes nothing: it is inside a {_KINDS.get(type(container), "container")} '
                  f"that {_label(top)} is not in (near {self.parsed[top][0].context!r})", element)
        else:
            warn(f"this :: closes nothing: no element is open (near {element.context!r})",
                  element)
        return None

    # -- the tree ---------------------------------------------------------------

    def build(self, text):
        document = Document(span=(0, len(self.source)))
        for node in self._replay(text.chars, text.origins, document):
            node.end_tag = False        # elements never closed: no closing tag
        self._spans(document)
        return document

    def _replay(self, chars, origins, root):
        """The nodes of a text of the stages, in `root`: its text between
        the events, the nodes the events open, close or are. The nodes left
        open at its end are returned."""
        stack = [root]
        below = [0]                     # for each node of the stack, the last one that is no Element
        buffer, buffer_origins = [], []

        def flush():
            if buffer:
                self._text_nodes(''.join(buffer), buffer_origins, stack[-1])
                buffer.clear()
                buffer_origins.clear()

        for ch, origin in zip(chars, origins):
            if origin >= 0:
                buffer.append(ch)
                buffer_origins.append(origin)
                continue
            flush()                     # an event: one character
            what, node = self.events[-origin - 1]
            if what == 'open':
                if isinstance(node, List):      # the elements open in the text of its item end here
                    k = below[-1]
                    if isinstance(stack[k], Item):
                        del stack[k + 1:], below[k + 1:]
                stack[-1].children.append(node)
                stack.append(node)
                below.append(below[-1] if isinstance(node, Element) else len(stack) - 1)
            elif what == 'leaf':
                stack[-1].children.extend(node if isinstance(node, list) else [node])
            else:                       # the elements still open in it end with it (warned)
                while stack[-1] is not node:
                    stack.pop()
                    below.pop()
                stack.pop()
                below.pop()
        flush()
        return stack[1:]

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

    def _expanded(self, raw, origins):
        """The text with what its placeholders of text (a URL, a group of
        what is not an element) hide, put back: the zones in them are zones
        (a code block in the {...} of a::b is a code block). Their characters
        are placed in the source, each where it is written."""
        if not any(m.group(1) in 'AU' for m in PLACEHOLDER.finditer(raw)):
            return raw, origins
        parts, places, position = [], [], 0
        for m in PLACEHOLDER.finditer(raw):
            if m.group(1) not in 'AU':
                continue
            parts.append(raw[position:m.start()])
            places.extend(origins[position:m.start()])
            entry = self.stores.hidden(m)
            entry, entry_places = self._expanded(entry, self._placed(entry, self.offsets[origins[m.start()]]))
            parts.append(entry)
            places.extend(entry_places)
            position = m.end()
        parts.append(raw[position:])
        places.extend(origins[position:])
        return ''.join(parts), places

    def _placed(self, text, start):
        """Origins for a text hidden by a placeholder whose source starts at
        `start`: new ones, added after the offsets of the prepared text (each
        character followed by the offset after it, as there)."""
        first = len(self.offsets)
        self.offsets.extend(self._offsets(text, start))     # and where the text ends
        return list(range(first, first + len(text)))

    def _text_nodes(self, raw, origins, parent):
        """Text, and the opaque zones its placeholders hold (a URL or a
        group hidden in a text is text: one node with the text around it)."""
        raw, origins = self._expanded(raw, origins)
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
            if isinstance(node, Text) and isinstance(last, Text) and last.span[1] == node.span[0] \
                    and last.line is not None and last not in self.built:
                last.value += node.value
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
        return self._located(Text(value=self.stores.original(raw)), origins)

    def _zone(self, m, origins):
        kind = m.group(1)
        original = self.stores.original(m.group(0))
        if kind == 'C':
            block = CODE_BLOCK.match(original)
            body = block.group('body')
            last = body.rfind('\n') + 1
            if last and not body[last:].strip():    # the indentation of an indented code::[-]
                body = body[:last]
            node = Code(language=code_language(block.group('header')), body=body)
        elif kind == 'I':
            node = InlineCode(text=original[1:-1])
        elif kind == 'R' and original.startswith(('\\(', '\\[')):
            node = Math(text=original, display=original.startswith('\\['))
        elif kind == 'R':
            raw_kind = ('comment' if original.startswith(('<!--', '{#')) else
                        'jinja' if original.startswith(('{{', '{%')) else
                        'script' if original[:7].lower() == '<script' else
                        'style' if original[:6].lower() == '<style' else 'html')
            node = Raw(text=original, raw_kind=raw_kind)
        else:                           # a URL or a group of an element that is not one: text
            return self._located(Text(value=original), origins)
        return self._located(node, origins)


# ---------------------------------------------------------------------------
# The public functions
# ---------------------------------------------------------------------------

# a word glued to a :: that ends its line or is followed by a space: a closing :: meant
# a heading written with a style or attributes: no heading
_HEADING_GROUP = re.compile(r'^=+[\[{].*', re.MULTILINE)
# the marks of bold and italic left after their stages, and the blank lines between paragraphs
_MARK = re.compile(r'\*\*|__|\n[ \t]*\n')
_GLUED_CLOSE = re.compile(r'(?<![\w:-])([A-Za-z][\w-]*)::(?=[ \t]*(?:\n|$))', re.MULTILINE)

_KINDS = {Heading: 'heading', List: 'list', Item: 'list item', Strong: 'bold', Emphasis: 'italic'}


def _label(node):
    return f'{node.written.tag}::'


def _tag_error(label, what, error, element):
    return LHTMLError(f'{label} its {what} raised {type(error).__name__}: {error} '
                      f"(near {element.context or label!r})", element.line, element.column)


def _registry(tags, macros):
    """The built-in TAGS, the macros, then the tags given (which win)."""
    if macros is not None and not isinstance(macros, Mapping):
        raise TypeError(f'macros: expected a mapping of definitions, got {type(macros).__name__} '
                        f'(the macros of files: lhtml.load_macros(path or [paths]))')
    registry = registry_with_macros(macros) if macros else dict(TAGS)
    for name, tag in (tags or {}).items():
        if not isinstance(tag, Tag):
            raise TypeError(f'tag {name!r}: expected an lhtml.Tag(build, container, url), '
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


def parse(text: str, *, macros: Mapping[str, Mapping | None] | None = None,
          tags: Mapping[str, Tag] | None = None, warn: bool = True) -> Document:
    """The document tree of an LHTML text. `macros`: the definitions of the
    macros, a mapping (lhtml.load_macros reads them from files); `tags`:
    {name: Tag}, added to the built-in TAGS and the macros (a tag given
    wins). Reads no file.

    The problems found are kept in document.problems (LHTMLWarning, in
    source order), and emitted as warnings unless `warn` is False; an
    LHTMLError raised holds those found before it in its `problems`. Each
    parse collects its own (threads and tasks included): no global state
    is changed."""
    registry = _registry(tags, macros)
    collected = []
    token = PROBLEMS.set(collected)
    try:
        parser = _Parser(text, registry)
        document = parser.parse()
    except LHTMLError as error:
        error.problems = _in_order(collected)
        raise
    finally:                            # emitted, an error raised or not
        PROBLEMS.reset(token)
        if warn:
            _emit(_in_order(collected))
    given = _given_offsets(text, parser.source)
    if given:
        for node in document.walk():
            node.span = (given(node.span[0]), given(node.span[1]))
    document.span = (0, len(text))
    document.problems = _in_order(collected)
    document.source = text
    return document


def _in_order(problems):
    return sorted(problems, key=lambda p: (p.line is None, p.line or 0, p.column or 0))


def _emit(problems):
    """The problems as warnings, at the first place of the caller outside
    LHTML (its call of run or parse)."""
    frame, package = sys._getframe(1), os.path.dirname(__file__)
    while frame is not None and os.path.dirname(frame.f_code.co_filename) == package:
        frame = frame.f_back
    filename, lineno, module = ('lhtml', 0, None) if frame is None else \
        (frame.f_code.co_filename, frame.f_lineno, frame.f_globals.get('__name__'))
    for problem in problems:
        warnings.warn_explicit(problem, LHTMLWarning, filename, lineno, module)
