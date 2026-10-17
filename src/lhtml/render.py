"""The HTML of a document tree, from the fields of its nodes alone
(nodes.py): render(document, line_breaks=False, media=None)."""

import html as _html
import re

from .attributes import quoted
from .code import export_html_code
from .nodes import Code, Element, Emphasis, Heading, InlineCode, Item, List, Math, Raw, Strong, Text, Video
from .patterns import PLACEHOLDER
from .process import ProtectionStores, escape_inline_code, line_breaks as _with_line_breaks, render_inline_code

_ZONES = (Code, InlineCode, Math, Raw)
_ESCAPE = '\x00Z0\x00'            # a \x00 of the text, apart from the placeholders of the zones


class _Holder:
    """A node as the only child of nothing (_tokens of one element)."""
    def __init__(self, node):
        self.children = [node]


def _video(node, media):
    """<video> with its sources: those of the resolver `media`, or its src."""
    source = node.src
    extension = source.rsplit('.', 1)[-1]
    mime_extension = re.split(r'[?#]', extension, maxsplit=1)[0].lower()
    sources = list(media(source) or []) if media is not None else []
    if not sources:
        sources = [(source, f'video/{mime_extension}')]
    parts = [f'<{node.name}{node.attributes.html()}>\n']
    for url, mime in sources:
        parts.append(f'\t<source src="{quoted(url)}" type="{quoted(mime)}">\n')
    parts.append(f'\t Cannot play video {_html.escape(source)}\n')
    parts.append(f'</{node.name}>')
    return ''.join(parts)


def _zone(node):
    if isinstance(node, Code):
        return export_html_code(node.body, node.language, warn=False)     # warned by parse
    if isinstance(node, InlineCode):
        return render_inline_code(escape_inline_code(node.text))
    return node.text                    # Math, Raw


def _leaf(node, media):
    """The HTML of a node that is written without its children (None: it
    holds them)."""
    if isinstance(node, Video):
        return _video(node, media)
    if isinstance(node, Element) and node.void:
        return f'<{node.name}{node.attributes.html()}>'
    return None


def _around(node):
    """(opening, closing) of a node that holds its children."""
    if isinstance(node, Heading):
        return f'<h{node.level}{node.attributes.html()}>', f'</h{node.level}>\n'
    if isinstance(node, List):
        return '<ul>\n', '</ul>\n'
    if isinstance(node, Item):
        return '<li>\n', '</li>\n'
    if isinstance(node, Strong):
        return '<strong>', '</strong>'
    if isinstance(node, Emphasis):
        return '<em>', '</em>'
    if isinstance(node, Element):
        return (f'<{node.name}{node.attributes.html()}>',
                '' if node.closed == 'never' else f'</{node.name}>')
    return '', ''                       # the document, a node of the caller


def _tokens(root, media, zone, pieces=True):
    """(html, kind) in order: kind 'text' (a Text), 'leaf' (`zone(node)`: a
    code block, raw HTML, mathematics, inline code) or 'markup' (what a node
    writes around its children, or an element written without them; one
    that holds nothing of what follows, a link and its label, is one piece
    with `pieces`). No
    recursion: a document may nest deeper than Python's recursion limit."""
    out, stack = [], [(iter([root]), None)]
    while stack:
        children, closing = stack[-1]
        node = next(children, None)
        if node is None:
            stack.pop()
            if closing:
                out.append((closing, 'markup'))
        elif isinstance(node, Text):
            out.append((node.value, 'text'))
        elif isinstance(node, _ZONES):
            out.append((zone(node), 'leaf'))
        elif (html := _leaf(node, media)) is not None:
            out.append((html, 'markup'))
        elif pieces and isinstance(node, Element) and node.closed in ('void', 'inline') and node.children:
            # its children are its own (a link label): one piece, its line breaks left as they are
            out.append((''.join(h for h, _ in _tokens(_Holder(node), media, _zone, pieces=False)), 'markup'))
        else:
            opening, closing = _around(node)
            if opening:
                out.append((opening, 'markup'))
            stack.append((iter(node.children), closing))
    return out


def render(document, *, line_breaks=False, media=None):
    """The HTML of a document tree (or of any node). `line_breaks`: the line
    breaks of the source are rendered as <br>; `media`: the resolver of the
    sources of a video, media(src) -> [(url, mime type)] (none: the source
    as written)."""
    if media is not None and not callable(media):
        raise TypeError(f'"media" must be callable, got {type(media).__name__}')
    if not line_breaks:
        return ''.join(html for html, _ in _tokens(document, media, _zone))
    # the zones are one piece each for the line breaks, then written
    stores, written = ProtectionStores(), {}

    def zone(node):
        kind = 'C' if isinstance(node, Code) else 'I' if isinstance(node, InlineCode) else 'R'
        placeholder = stores.add(kind, (node.language, node.body) if kind == 'C' else
                                 getattr(node, 'text', ''))
        written[placeholder] = _zone(node)
        return placeholder
    tokens = [(html if kind == 'leaf' else html.replace('\x00', _ESCAPE), kind)
              for html, kind in _tokens(document, media, zone)]
    text = _with_line_breaks(tokens, stores)
    return PLACEHOLDER.sub(lambda m: '\x00' if m.group(0) == _ESCAPE else written.get(m.group(0), m.group(0)),
                           text)
