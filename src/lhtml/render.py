"""The HTML of a document tree, from the fields of its nodes alone
(nodes.py): render(document, line_breaks=False, media=None)."""

from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
import re

from .attributes import Attributes, quoted
from .code import export_html_code
from .nodes import Code, Element, Emphasis, Heading, InlineCode, Item, List, Math, Raw, Strong, Text, Video
from .patterns import BLOCK_RAW, BLOCK_TAGS, JINJA_LINE, LEADING_TAG, PREFORMATTED_TAG
from .process import escape_inline_code, render_inline_code

_ZONES = (Code, InlineCode, Math, Raw)
_PREFORMATTED = ('pre', 'textarea')     # their line breaks are visible already


def _attributes(node):
    """The HTML of the attributes of a node: an Attributes, or a mapping the
    caller set since (node.attributes = {...})."""
    attributes = node.attributes
    if attributes is None:
        return ''
    if not isinstance(attributes, Attributes):
        if not isinstance(attributes, Mapping):
            raise TypeError(f'{node.kind}: attributes must be a mapping or lhtml.Attributes, '
                            f'got {type(attributes).__name__}')
        attributes = Attributes(attributes)
    return attributes.html()


def _video(node, media):
    """<video> with its sources: those of the resolver `media`, or its src."""
    source = node.src
    extension = source.rsplit('.', 1)[-1]
    mime_extension = re.split(r'[?#]', extension, maxsplit=1)[0].lower()
    sources = list(media(source) or []) if media is not None else []
    if not sources:
        sources = [(source, f'video/{mime_extension}')]
    parts = [f'<{node.name}{_attributes(node)}>\n']
    for url, mime in sources:
        parts.append(f'\t<source src="{quoted(url)}" type="{quoted(mime)}">\n')
    parts.append(f'\t Cannot play video {escape(source)}\n')
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
        return f'<{node.name}{_attributes(node)}>'
    return None


def _around(node):
    """(opening, closing) of a node that holds its children."""
    if isinstance(node, Heading):
        return f'<h{node.level}{_attributes(node)}>', f'</h{node.level}>\n'
    if isinstance(node, List):
        return '<ul>\n', '</ul>\n'
    if isinstance(node, Item):
        return '<li>\n', '</li>\n'
    if isinstance(node, Strong):
        return '<strong>', '</strong>'
    if isinstance(node, Emphasis):
        return '<em>', '</em>'
    if isinstance(node, Element):
        return f'<{node.name}{_attributes(node)}>', f'</{node.name}>' if node.end_tag else ''
    return '', ''                       # the document, a node of the caller


def _is_block(node):
    """Whether a node is a block at the edge of a line: a heading, a list,
    an item, a block element (div::, a macro of a block element), a code
    block; raw HTML that starts with a block tag, a comment, <script>,
    <style>, display mathematics, a Jinja statement or comment (the raw
    zones are read as written: they are the source)."""
    if isinstance(node, (Heading, List, Item, Code)):
        return True
    if isinstance(node, Element):
        return node.name.lower() in BLOCK_TAGS
    if isinstance(node, (Raw, Math)):
        if BLOCK_RAW.match(node.text) or JINJA_LINE.fullmatch(node.text):
            return True
        m = LEADING_TAG.match(node.text)
        return bool(m) and m.group(1).lower() in BLOCK_TAGS
    return False


def _preformatted(node, closing=False):
    """+1 where a <pre> or a <textarea> opens, -1 where it closes."""
    if isinstance(node, Element) and node.name.lower() in _PREFORMATTED:
        return -1 if closing else 1
    if isinstance(node, Raw):           # <pre> written as raw HTML
        m = PREFORMATTED_TAG.match(node.text)
        return (-1 if m.group(1) else 1) if m else 0
    return 0


@dataclass(slots=True)
class _Piece:
    """A piece of the HTML. `kind`: 'text' (of a Text: its line breaks are
    those of the source), 'zone' (a code block, raw HTML, mathematics,
    inline code: its lines are its own) or 'markup' (what a node writes
    around its children, or an element written without them). `block`: a
    block starts or ends here; `preformatted`: +1 where a <pre> opens, -1
    where it closes; `whole`: an element with its content (it ends where
    its HTML ends)."""
    html: str
    kind: str
    block: bool = False
    preformatted: int = 0
    whole: bool = False


def _link(node):
    return isinstance(node, Element) and node.name.lower() == 'a'


def _pieces(root, media):
    """The pieces of the HTML of a tree, in order, in one walk with its own
    stack (no recursion: a document may nest deeper than Python's
    recursion limit). Each node is opened, its children visited, then it is
    closed. In a link (<a>) every piece is markup: its label is one label,
    its line breaks are not made visible."""
    out, stack, links = [], [(iter([root]), None, False)], 0
    while stack:
        children, closing, link = stack[-1]
        node = next(children, None)
        if node is None:
            stack.pop()
            links -= link
            if closing is not None:
                out.append(closing)
            continue
        if links:                       # in a label: markup only
            if isinstance(node, Text):
                out.append(_Piece(node.value, 'markup'))
            elif isinstance(node, _ZONES):
                out.append(_Piece(_zone(node), 'markup'))
            elif (html := _leaf(node, media)) is not None:
                out.append(_Piece(html, 'markup'))
            else:
                opening, ending = _around(node)
                out.append(_Piece(opening, 'markup'))
                stack.append((iter(node.children), _Piece(ending, 'markup'), False))
            continue
        if isinstance(node, Text):
            out.append(_Piece(node.value, 'text'))
        elif isinstance(node, _ZONES):
            out.append(_Piece(_zone(node), 'zone', _is_block(node), _preformatted(node), True))
        elif (html := _leaf(node, media)) is not None:
            out.append(_Piece(html, 'markup', _is_block(node), 0, True))
        else:
            opening, ending = _around(node)
            block, link = _is_block(node), _link(node)
            out.append(_Piece(opening, 'markup', block, _preformatted(node), False))
            stack.append((iter(node.children),
                          _Piece(ending, 'markup', block, _preformatted(node, True), False), link))
            links += link
    return out


def _with_line_breaks(tokens):
    """The HTML of the pieces, the line breaks of the source made visible
    with <br>.

    A line is structure when its first or last piece is a block, or inside
    <pre> and <textarea>, whose line breaks are visible already (and on
    the line that opens or closes one). In each run of other lines, blank
    lines at the start and end of the run are ignored, and every line but
    the last one gets a <br>, blank lines included - if its line break is
    one of the source (in a Text): the line breaks a tag writes in its own
    HTML (video::) get none, and a zone is one piece (its lines are its own).
    """
    lines, ends, changes = [[]], [], [0]
    for token in tokens:
        changes[-1] += token.preformatted
        pieces = [token.html] if token.kind == 'zone' else token.html.split('\n')
        last = max((k for k, piece in enumerate(pieces) if piece), default=0)
        # a block starts on its first line, and ends on its last one when it is
        # whole or on one line (an opening tag on two lines ends nowhere)
        ends_here = token.whole or sum(1 for piece in pieces if piece) == 1
        block = token.block
        for k, piece in enumerate(pieces):
            if k:
                ends.append(token.kind)
                lines.append([])
                changes.append(0)
            if piece:                   # a tag on several lines (a style on two lines) is a block
                lines[-1].append((piece, block and k == 0, block and ends_here and k == last))
    texts = [''.join(piece for piece, *_ in line) for line in lines]
    structure, depth = [], 0
    for line, change in zip(lines, changes):
        edges = [(starts, ends_) for piece, starts, ends_ in line if piece.strip()]
        structure.append(depth > 0 or change != 0 or bool(edges) and (edges[0][0] or edges[-1][1]))
        depth = max(0, depth + change)
    blank = [not text.strip() for text in texts]
    start = 0
    while start < len(lines):
        if structure[start]:
            start += 1
            continue
        end = start
        while end < len(lines) and not structure[end]:
            end += 1
        first, last = start, end - 1    # the run, without its blank lines at the ends
        while first <= last and blank[first]:
            first += 1
        while last >= first and blank[last]:
            last -= 1
        for k in range(first, last):
            if ends[k] == 'text':
                texts[k] += '<br>'
        start = end
    return '\n'.join(texts)


def render(document, *, line_breaks=False, media=None):
    """The HTML of a document tree (or of any node). `line_breaks`: the line
    breaks of the source are rendered as <br>; `media`: the resolver of the
    sources of a video, media(src) -> [(url, mime type)] (none: the source
    as written)."""
    if media is not None and not callable(media):
        raise TypeError(f'"media" must be callable, got {type(media).__name__}')
    pieces = _pieces(document, media)
    if not line_breaks:
        return ''.join(piece.html for piece in pieces)
    return _with_line_breaks(pieces)
