"""The nodes of the document tree (lhtml.parse gives it, lhtml.render
writes its HTML from these fields alone: change a node, the HTML changes).

Every node has its `span`, the offsets of its source in the text given to
parse, `line` and `column` (1-based) of its start, and its `children`. A
node made by the caller, or by a tag, may have no place (line None).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .attributes import Attributes


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
    source: str = field(default='', repr=False)     # the text given to parse


@dataclass(eq=False)
class Text(Node):
    value: str = ''                 # written as it is (LHTML escapes nothing)


@dataclass(eq=False)
class Heading(Node):
    level: int = 1
    attributes: Attributes = field(default_factory=Attributes)
    written: str = ''               # its (.class #id) as written in the source (information)


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
    """An HTML element: <name attributes>children</name>.

    `void`: an element without content nor closing tag (<img>, <hr>).
    `closed`: how the source ends it - 'tag' (its ::), 'inline'
    (div::text::), 'void' (it holds nothing), 'container' (the end of the
    heading, item, bold or italic it is opened in), 'never' (not closed:
    no closing tag is written). `tag`: the LHTML tag written (`img`, a
    macro, '' for a bare ::); `written`: its groups and the word after them
    as written in the source ('()', '[]', '{}', 'text'). Both are
    information on the source: render reads name, attributes, children."""
    name: str = 'div'
    attributes: Attributes = field(default_factory=Attributes)
    void: bool = False
    closed: str = 'tag'
    tag: str = ''
    written: dict = field(default_factory=dict)


@dataclass(eq=False)
class Video(Element):
    """<video attributes> with its sources: those the `media` resolver of
    render gives for `src`, or `src` itself."""
    name: str = 'video'
    src: str = ''


@dataclass(eq=False)
class Code(Node):
    language: str = ''
    body: str = ''


@dataclass(eq=False)
class InlineCode(Node):
    text: str = ''                  # as written between the backquotes


@dataclass(eq=False)
class Math(Node):
    text: str = ''                  # with its \( \) or \[ \]
    display: bool = False


@dataclass(eq=False)
class Raw(Node):
    """HTML written as it is: raw HTML of the source, a comment, a script, a
    style, Jinja, or HTML a tag gives."""
    text: str = ''
    raw_kind: str = 'html'          # html, comment, script, style, jinja
