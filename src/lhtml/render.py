"""The HTML of a document tree, from the fields of its nodes alone
(nodes.py): render(document, line_breaks=False, media=None)."""

from html import escape
import re

from .attributes import quoted
from .code import export_html_code
from .nodes import Code, Element, Emphasis, Heading, InlineCode, Item, List, Math, Raw, Strong, Text, Video
from .patterns import BLOCK_RAW, BLOCK_TAGS, JINJA_LINE, LEADING_TAG, PREFORMATTED_TAG
from .process import escape_inline_code, render_inline_code

_ZONES = (Code, InlineCode, Math, Raw)
_PREFORMATTED = ('pre', 'textarea')     # their line breaks are visible already


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


def _tokens(root, media):
    """The pieces of the HTML of a tree, in order: (html, kind, block,
    preformatted, whole). `whole`: an element with its children and its
    closing tag (it ends where its HTML ends). kind 'text' (a Text: its line breaks are those of the
    source), 'zone' (a code block, raw HTML, mathematics, inline code: one
    piece, its lines its own) or 'markup' (what a node writes around its
    children, or an element written without them; one that holds nothing
    of what follows, a link and its label, is one piece). No recursion: a
    document may nest deeper than Python's recursion limit."""
    out, stack = [], [(iter([root]), None)]
    while stack:
        children, closing = stack[-1]
        node = next(children, None)
        if node is None:
            stack.pop()
            if closing:
                out.append(closing)
        elif isinstance(node, Text):
            out.append((node.value, 'text', False, 0, False))
        elif isinstance(node, _ZONES):
            out.append((_zone(node), 'zone', _is_block(node), _preformatted(node), True))
        elif (html := _leaf(node, media)) is not None:
            out.append((html, 'markup', _is_block(node), 0, True))
        elif isinstance(node, Element) and node.closed in ('void', 'inline') and node.children:
            out.append((_html(node, media), 'markup', _is_block(node), 0, True))
        else:
            opening, closing = _around(node)
            block = _is_block(node)
            if opening:
                out.append((opening, 'markup', block, _preformatted(node), False))
            stack.append((iter(node.children), (closing, 'markup', block, _preformatted(node, True), False)
                          if closing else None))
    return out


def _html(node, media):
    """The HTML of an element and its children, one piece."""
    opening, closing = _around(node)
    return opening + ''.join(html for child in node.children for html, *_ in _tokens(child, media)) + closing


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
    for html, kind, block, preformatted, whole in tokens:
        changes[-1] += preformatted
        pieces = [html] if kind == 'zone' else html.split('\n')
        last = max((k for k, piece in enumerate(pieces) if piece), default=0)
        # a block starts on its first line, and ends on its last one when it is
        # whole or on one line (an opening tag on two lines ends nowhere)
        ends_here = whole or sum(1 for piece in pieces if piece) == 1
        for k, piece in enumerate(pieces):
            if k:
                ends.append(kind)
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
    tokens = _tokens(document, media)
    if not line_breaks:
        return ''.join(html for html, *_ in tokens)
    return _with_line_breaks(tokens)
