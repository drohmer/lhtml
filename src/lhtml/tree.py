"""The document tree of LHTML (prototype of step N5): parse, then render.

    document = parse(text, tags=None, macros=None)
    html     = render(document, meta=None)

The tree nests what the passes of `run` wrote as flat HTML: headings,
lists, bold and italic, the `::` elements, and the zones LHTML never reads
(code, inline code, mathematics, raw HTML, Jinja) as opaque leaves. Every
node has its `span`, the offsets of its source in the text given to parse,
and `line`, `column` exact by construction.

How it parses: the stages are those of `run` (protection, headings, lists,
bold, italic, elements), over the same intermediate text, so that what is a
heading, an item or an element is decided exactly as `run` decides it. But
each character of that text keeps its origin - a character of the source,
or the markup a node generated - and the elements are recorded as events
instead of being written as HTML. The tree is built from those events, and
`render` writes the HTML from the tree alone.

What the tree changes: an element opened in a heading, a list item, a bold
or an italic span, and not closed there (its `::` elsewhere, or none), is
closed at the end of that container, with a warning; its `::`, if any,
closes nothing (a warning, and the `::` stays as text). `run` writes the
same text as malformed HTML (<li><span>...</li>...</span>).
"""

from __future__ import annotations

import bisect
import re
import warnings
from dataclasses import dataclass, field
from typing import Callable

from .errors import LHTMLParseError, LHTMLWarning
from .export_html import (
    export_html_element_class_and_id, export_html_generic, export_html_img,
    export_html_link, export_html_video, _build_attrs,
)
from .macros import VOID_TAGS, _check, _attr, load_macros
from .patterns import (
    BOLD, HEADING, ITALIC, PLACEHOLDER, TAG_MARKER,
)
from .process import (
    ProtectionStores, normalize_input, process_prepare, process_unprotect,
    process_line_breaks, render_inline_code, render_code_block, _code_language,
    _is_tag_boundary, _adjust_bare_tag, _context, _warn, check_is_closing_tag,
)
from .tag_parser import extract_bracket_elements, _TAG_NAME_BEFORE, _MAX_TAG_NAME
from .wrap_html import wrap_auto


# ---------------------------------------------------------------------------
# The nodes
# ---------------------------------------------------------------------------

@dataclass(eq=False)
class Node:
    span: tuple = (0, 0)            # offsets in the text given to parse
    line: int | None = None
    column: int | None = None
    children: list = field(default_factory=list)
    # False when the markup of the node is in the text of an element (a
    # bold opened in the label of a link::u[**b] and closed after it): the
    # element writes it, the node does not write it again
    open_tag: bool = field(default=True, repr=False)
    close_tag: bool = field(default=True, repr=False)

    @property
    def kind(self):
        return type(self).__name__

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


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
    closed: str = 'tag'             # 'tag' (by ::), 'inline' or 'void' (no children), 'never', 'container'
    element: dict = field(default_factory=dict, repr=False)     # what the tag renders from


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
    store: str = 'R'
    index: int = 0


# ---------------------------------------------------------------------------
# The tags
# ---------------------------------------------------------------------------

@dataclass
class Tag:
    """A `name::` tag. `container`: whether it holds what follows until its
    `::` (a bool, or a function of the element: div::text:: closes at once).
    `render(element, children, context)`: its HTML, closing tag included;
    `children` is the HTML of what it holds ('' for a void or inline one),
    and element['closed'] is False when nothing closed it."""
    render: Callable
    container: bool | Callable = False
    html: str = 'div'               # the HTML tag it opens, for the warnings

    def holds(self, element):
        return self.container(element) if callable(self.container) else bool(self.container)


def _close(html, tag, element):
    return html + (f'</{tag}>' if element.get('closed', True) else '')


def generic(tag):
    """div::, span::: holds what follows, unless written div::text::"""
    def render(element, children, context):
        text = element['text']
        if text.endswith('::'):
            return f'<{tag}{_build_attrs(element)}>{text[:-2]}</{tag}>'
        return _close(f'<{tag}{_build_attrs(element)}>{text}' + children, tag, element)
    return Tag(render, container=lambda element: not element['text'].endswith('::'), html=tag)


TAGS = {
    'div': generic('div'),
    'span': generic('span'),
    'link': Tag(lambda element, children, context: export_html_link(element)),
    'img': Tag(lambda element, children, context: export_html_img(element)),
    'video': Tag(lambda element, children, context: export_html_video(element, '', context.media)),
    'videoplay': Tag(lambda element, children, context: export_html_video(
        element, 'autoplay loop muted playsinline', context.media)),
}

_SPACER = Tag(lambda element, children, context: '<div style="height:1em;"></div>')


def macro_tag(name, spec):
    """The Tag of a macro definition (lhtml.macros): the element of its tag,
    with the defaults of the macro added to those of the source."""
    spec = _check(name, spec)
    tag = spec.get('tag') or 'div'
    void = tag.lower() in VOID_TAGS
    classes = (spec.get('class') or '').split()
    attrs = (spec.get('attrs') or '').strip()
    empty = bool(spec.get('empty', False))
    url = spec.get('url')
    variant = spec.get('variant')
    default = spec.get('default')

    def merged(element, warn):
        text = element['text']
        all_classes = list(classes)
        if variant:
            value = text.strip()
            closed = value.endswith('::')
            if closed:
                value = value[:-2].strip()
            value = value or (str(default) if default is not None else '')
            if value:
                if warn and value not in [str(v) for v in variant]:
                    _warn(f'{name}::{value}: unknown variant (expected one of '
                          f'{", ".join(str(v) for v in variant)}) near {element.get("context", "")!r}',
                          element, stacklevel=5)
                all_classes.append(f'{classes[0]}-{value}')
            text = '::' if closed else ''
        inline = ' '.join(a for a in (attrs, element['{}']) if a)
        if url:
            closed = text.rstrip().endswith('::')
            value = text.rstrip()[:-2] if closed else text
            inline = ' '.join(a for a in (f'{url}="{_attr(value.strip())}"', inline) if a)
            text = '::' if closed else ''
        result = {**element,
                  '()': ' '.join(['.' + c for c in all_classes] + ([element['()']] if element['()'] else [])),
                  '{}': inline, 'text': text}
        if not void and empty and not result['text'].endswith('::'):
            result['text'] += '::'
        return result

    def holds(element):
        return not void and not merged(element, warn=True)['text'].endswith('::')

    def render(element, children, context):
        m = merged(element, warn=False)
        if void:
            return f'<{tag}{_build_attrs(m)}>' + ('' if m['text'] == '::' else m['text'])
        text = m['text']
        if text.endswith('::'):
            return f'<{tag}{_build_attrs(m)}>{text[:-2]}</{tag}>'
        return _close(f'<{tag}{_build_attrs(m)}>{text}' + children, tag, element)

    return Tag(render, container=holds, html=tag)


def tags_with_macros(macros, base=None):
    """The tags and the Tags of the macros (a mapping, a YAML file, or a list)."""
    tags = dict(TAGS if base is None else base)
    for name, spec in load_macros(macros).items():
        tags[name] = macro_tag(name, spec)
    return tags


# ---------------------------------------------------------------------------
# The text of the stages, each character with its origin
# ---------------------------------------------------------------------------

EVENT_CHAR = '\ue000'           # an element, once recorded: one character of the text

class _Text:
    """A text and the origin of each of its characters: an offset of the
    prepared text (>= 0), or -(k + 1) for the k-th event (markup a node
    wrote: '<h1>', '<li>\\n', an element)."""

    def __init__(self, chars, origins):
        self.chars, self.origins = chars, origins

    def transform(self, pattern, pieces):
        """For each match of `pattern`, the pieces it becomes: (start, end)
        kept from the text, or (generated text, event)."""
        chars, origins, prev = [], [], 0
        for m in pattern.finditer(self.chars):
            chars.append(self.chars[prev:m.start()])
            origins.extend(self.origins[prev:m.start()])
            for piece in pieces(m):
                if isinstance(piece[0], int):
                    a, b = piece
                    chars.append(self.chars[a:b])
                    origins.extend(self.origins[a:b])
                else:
                    text, event = piece
                    chars.append(text)
                    origins.extend([-(event + 1)] * len(text))
            prev = m.end()
        chars.append(self.chars[prev:])
        origins.extend(self.origins[prev:])
        return _Text(''.join(chars), origins)


class _Parser:

    def __init__(self, text, tags, context):
        self.source = normalize_input(text)
        self.tags = tags
        self.context = context
        self.stores = ProtectionStores()
        self.events = []            # (what, node): 'open', 'close', 'leaf'
        self.swallowed = {}         # element event: the events in its text (a link label)
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

    # -- the stages ---------------------------------------------------------

    def parse(self):
        prepared = process_prepare(self.source, self.stores)
        self.offsets = self._prepared_offsets(prepared)
        text = _Text(prepared, list(range(len(prepared))))
        text = self.headings(text)
        text = self.lists(text)
        text = self.inline(text, BOLD, Strong, 'strong')
        text = self.inline(text, ITALIC, Emphasis, 'em')
        text = self.elements(text)
        return self.build(text)

    def headings(self, text):
        def pieces(m):
            level = len(m.group(1))
            class_id = self.stores.restore(m.group(2) or '', 'A').strip()
            attrs = export_html_element_class_and_id(class_id) if class_id else ''
            if attrs:
                attrs = self.stores.add('A', attrs)
            node = Heading(level=level, attributes=class_id)
            span = self.source_of(text.origins[m.start():m.end()]) or (0, 0)
            node.span = span
            node.line, node.column = self.place(span[0])
            return [(f'<h{level}{attrs}>', self.event('open', node)), (m.start(3), m.end(3)),
                    (f'</h{level}>\n', self.event('close', node))]
        return text.transform(HEADING, pieces)

    def lists(self, text):
        """`* item` lines, as process_listing reads them: a run of them is a
        list, a deeper level a list inside an item of its own."""
        chars, origins = [], []

        def gen(s, event):
            chars.append(s)
            origins.extend([-(event + 1)] * len(s))

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
            levels.append(len(m.group(1)) if m and '\n' not in m.group(0) else 0)
        stack, level = [], 0            # the open List and wrapper Item nodes
        for k, (a, b) in enumerate(lines):
            line_level = levels[k]
            while level < line_level:
                level += 1
                if level > 1:
                    wrapper = Item()
                    gen('<li>\n', self.event('open', wrapper))
                    stack.append(wrapper)
                lst = List()
                gen('<ul>\n', self.event('open', lst))
                stack.append(lst)
            if level > 0:
                node = Item()
                m = item.match(text.chars, a, b)
                gen('<li>\n', self.event('open', node))
                end = m.end(2)
                chars.append(text.chars[m.start(2):end])
                origins.extend(text.origins[m.start(2):end])
                if end < len(text.chars) and text.chars[end] == '\n':
                    chars.append('\n')
                    origins.append(text.origins[end])
                    gen('</li>\n', self.event('close', node))
                else:                   # the last line: its line break is written, as content
                    gen('\n', self.event('leaf', Text(value='\n', raw='\n')))
                    gen('</li>\n', self.event('close', node))
                span = self.source_of(text.origins[a:b])
                if span:
                    node.span = span
                    node.line, node.column = self.place(span[0])
            else:
                chars.append(text.chars[a:b])
                origins.extend(text.origins[a:b])
            next_level = levels[k + 1] if k + 1 < len(lines) else 0
            while level > next_level:
                level -= 1
                gen('</ul>\n', self.event('close', stack.pop()))
                if level >= 1:
                    gen('</li>\n', self.event('close', stack.pop()))
        return _Text(''.join(chars), origins)

    def inline(self, text, pattern, kind, html):
        def pieces(m):
            node = kind()
            span = self.source_of(text.origins[m.start():m.end()])
            if span:
                node.span = span
                node.line, node.column = self.place(span[0])
            return [(f'<{html}>', self.event('open', node)), (m.start(1), m.end(1)),
                    (f'</{html}>', self.event('close', node))]
        return text.transform(pattern, pieces)

    def elements(self, text):
        """The `::` elements, decided as process_tag decides them, recorded
        as events: an element's source becomes one event, and its `::` another."""
        chars, origins = [], []
        prev, last_tag_end = 0, -1
        stack = []                      # the open Element nodes, as tag_to_close
        resolve = lambda s: self.stores.restore(self.stores.restore(s, 'A'), 'U')
        flat = self._flat(text)
        for m in TAG_MARKER.finditer(flat):
            if m.start() < prev:
                continue
            line, column = self._place_of(text, m.start())
            try:
                element = extract_bracket_elements(flat, m.end())
            except LHTMLParseError as e:
                found = _TAG_NAME_BEFORE.search(flat, max(0, m.start() - _MAX_TAG_NAME), m.start())
                name = len(found.group()) if found else 0
                _warn(f'{e} near {_context(flat, m.start() - name, m.end() + 30)!r}',
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
            context = resolve(flat[tag_start:element['index_end']])
            element['context'] = _context(context, 0, len(context))
            for key in ('text', '[]', '()', '{}'):
                element[key] = resolve(element[key])
            what = self._decide(element, stack)
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
            inside = [-o - 1 for o in text.origins[tag_start:element['index_end']] if o < 0]
            event = self.event(kind, node)
            self.swallowed[event] = list(dict.fromkeys(inside))
            chars.append(EVENT_CHAR)
            origins.append(-(event + 1))
            prev = last_tag_end = element['index_end']
        for node in stack:
            _warn(f"Tag <{self._html_name(node)}> is never closed (near {node.element['context']!r})",
                  node.element)
        chars.append(text.chars[prev:])
        origins.extend(text.origins[prev:])
        return _Text(''.join(chars), origins)

    @staticmethod
    def _flat(text):
        """The text as the passes of `run` wrote it: the markup of the
        nodes is HTML there ('<h1>', '<strong>'), and the decisions of the
        tag pass read it."""
        return text.chars

    def _place_of(self, text, position):
        origin = text.origins[position]
        if origin < 0:
            return None, None
        return self.place(self.offsets[origin])

    @staticmethod
    def _html_name(node):
        return node.tag.html

    def _decide(self, element, stack):
        """(event, node) of an element, as _dispatch_tag decides it; None
        when it is not a tag (its source stays)."""
        tag = element['tag']
        if element['[]'] == '-' and tag != 'link':
            from .process import _refuse_explicit_closing
            _refuse_explicit_closing(element)
        if tag:
            handler = self.tags.get(tag)
            if handler is None:
                return None
            return self._open(element, handler, tag, stack)
        if check_is_closing_tag(element):
            if not stack:
                _warn(f"Closing tag :: has no matching opening tag (near {element.get('context', '')!r})",
                      element, stacklevel=4)
                return None
            return 'close', stack.pop()
        if element['text'] == 'nl':
            return 'leaf', self._element(element, _SPACER, '', 'void')
        if element['[]'] or element['()'] or element['{}'] or element['text']:
            return self._open(element, TAGS['div'], '', stack)
        return None

    def _open(self, element, handler, name, stack):
        if handler.holds(element):
            node = self._element(element, handler, name, 'tag')
            stack.append(node)
            return 'open', node
        closed = 'inline' if element['text'].endswith('::') else 'void'
        return 'leaf', self._element(element, handler, name, closed)

    @staticmethod
    def _element(element, handler, name, closed):
        node = Element(name=name, groups={k: element[k] for k in ('[]', '()', '{}')},
                       value=element['text'], closed=closed, element=element)
        node.tag = handler
        return node

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
            opened = self._swallow(event, stack, done)
            what, node = self.events[event]
            if what == 'open':
                stack[-1].children.append(node)
                stack.append(node)
            elif what == 'leaf':
                stack[-1].children.append(node)
            elif what == 'close':
                self._close(node, stack)
            for node in opened:         # a markup opened in the text of the element
                node.open_tag = False
                stack[-1].children.append(node)
                stack.append(node)
        flush()
        while len(stack) > 1:           # elements never closed: as run leaves them
            node = stack.pop()
            if isinstance(node, Element):
                node.closed = 'container' if getattr(node, 'pending', False) else 'never'
        self._spans(document)
        return document

    def _swallow(self, event, stack, done):
        """The markup of the nodes written in the text of an element (the
        label of a link): a node closed there ends before the element, and
        does not write its closing tag; one opened there starts after it
        (returned), and does not write its opening tag."""
        opened = []
        for inner in self.swallowed.get(event, ()):
            done.add(inner)
            what, node = self.events[inner]
            if what == 'open':
                opened.append(node)
            elif what == 'close':
                if node in opened:      # all of it in the text: not a node of the tree
                    opened.remove(node)
                elif node in stack:
                    self._close(node, stack)
                    node.close_tag = False
        return opened

    def _close(self, node, stack):
        if node not in stack:           # closed already, at the end of its container
            if isinstance(node, Element):
                _warn(f'{node.element["context"]}: this :: closes nothing: its element was closed at '
                      f'the end of the heading, list item, bold or italic it was opened in', node.element)
                stack[-1].children.append(Text(value='::', raw='::'))
            return
        if isinstance(node, Element) and any(not isinstance(n, Element) for n in stack[stack.index(node) + 1:]):
            # its :: is inside a heading, an item, a bold opened after it:
            # it closes nothing, and the element ends with its own container
            _warn(f'{node.element["context"]}: its :: is inside a heading, list item, bold or italic '
                  f'opened after it, and closes nothing: the element is closed at the end of its '
                  f'own container', node.element)
            stack[-1].children.append(Text(value='::', raw='::'))
            node.pending = True
            return
        while stack[-1] is not node:
            inner = stack.pop()
            if isinstance(inner, Element):
                if not isinstance(node, Element):
                    inner.closed = 'container'
                    _warn(f'{inner.element["context"]}: closed at the end of the {node.kind.lower()} it is '
                          f'opened in (its :: is elsewhere, or missing)', inner.element)
                elif getattr(inner, 'pending', False):
                    inner.closed = 'container'
        stack.pop()

    def _spans(self, node):
        """A node that has no source of its own (a list, a wrapper item)
        spans its children; an element spans them too when it holds them."""
        for child in node.children:
            self._spans(child)
        if node.children and not isinstance(node, Document):
            first, last = node.children[0].span, node.children[-1].span
            if node.span == (0, 0):
                node.span = (first[0], last[1])
                node.line, node.column = self.place(first[0])
            else:
                node.span = (min(node.span[0], first[0]), max(node.span[1], last[1]))

    def _text_nodes(self, raw, origins, parent):
        """Text, and the opaque zones its placeholders hold."""
        position = 0
        for m in PLACEHOLDER.finditer(raw):
            if m.start() > position:
                parent.children.append(self._text(raw[position:m.start()], origins[position:m.start()]))
            parent.children.append(self._zone(m, origins[m.start():m.end()]))
            position = m.end()
        if position < len(raw):
            parent.children.append(self._text(raw[position:], origins[position:]))

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

def parse(text, tags=None, macros=None, context=None):
    """The document tree of an LHTML text. `tags`: {name: Tag} added to the
    built-in TAGS; `macros`: definitions of macros (lhtml.macros). Reads no
    file but the macro files named. The warnings are emitted, and kept in
    document.problems."""
    registry = dict(TAGS)
    if macros:
        registry = tags_with_macros(macros, registry)
    registry.update(tags or {})
    caught = []
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            document = _Parser(text, registry, context).parse()
    finally:                            # emitted, an error raised or not
        for w in caught:
            warnings.warn_explicit(w.message, w.category, w.filename, w.lineno)
    document.problems = [w.message for w in caught]
    return document


_MARKUP = {
    Heading: lambda node: (f'<h{node.level}'
                           + (export_html_element_class_and_id(node.attributes) if node.attributes else '')
                           + '>', f'</h{node.level}>\n'),
    List: lambda node: ('<ul>\n', '</ul>\n'),
    Item: lambda node: ('<li>\n', '</li>\n'),
    Strong: lambda node: ('<strong>', '</strong>'),
    Emphasis: lambda node: ('<em>', '</em>'),
}


def _render_node(node, context):
    if isinstance(node, Text):
        return node.raw
    if isinstance(node, (Code, InlineCode, Math, Raw)):
        store = 'C' if isinstance(node, Code) else 'I' if isinstance(node, InlineCode) else 'R'
        return f'\x00{store}{node.index}\x00'
    children = ''.join(_render_node(child, context) for child in node.children)
    markup = _MARKUP.get(type(node))
    if markup is not None:
        opening, closing = markup(node)
        return (opening if node.open_tag else '') + children + (closing if node.close_tag else '')
    if isinstance(node, Element):
        element = {**node.element, 'closed': node.closed != 'never'}
        return node.tag.render(element, children, context)
    return children


def render(document, meta=None, media=None):
    """The HTML of a document tree, with the options of `run` (line-breaks,
    wrap-auto, title, css, js) and the media resolver."""
    from .pipeline import ProcessingContext
    meta = dict(meta or {})
    context = ProcessingContext(meta, media if media is not None else meta.get('media'))
    stores = document.stores
    text = ''.join(_render_node(child, context) for child in document.children)
    text = stores.restore(text, 'I', render_inline_code)
    if meta.get('line-breaks') is True:
        text = process_line_breaks(text, stores)
    text = process_unprotect(text, stores)
    text = stores.restore(text, 'C', render_code_block)
    if meta.get('wrap-auto') is True:
        text = wrap_auto(text, meta)
    return text


def run(text, meta=None, tags=None):
    """`lhtml.run` through the tree: parse, then render."""
    import os
    meta = dict(meta or {})
    macros = meta.get('macros')
    if macros:
        directory = str(meta.get('current_directory') or '')
        macros = [m if not isinstance(m, str) or os.path.isabs(m) else os.path.join(directory, m)
                  for m in (macros if isinstance(macros, (list, tuple)) else [macros])]
    media = meta.get('media')
    if media is not None and not callable(media):
        raise TypeError(f'meta "media" must be callable, got {type(media).__name__}')
    from .pipeline import ProcessingContext
    context = ProcessingContext(meta, media)
    document = parse(text, tags=tags, macros=macros, context=context)
    return render(document, meta, media)
