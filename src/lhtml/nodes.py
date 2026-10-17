"""The nodes of the document tree (lhtml.parse gives it, lhtml.render
writes its HTML from these fields alone: change a node, the HTML changes).

Every node has its `children`, and its place in the text given to parse:
`span`, the offsets of its source, `line` and `column` (1-based) of its
start. They are keyword arguments, so a node is made as it reads:
Text('Hello'), Element('div', {'class': 'note'}, children=[...]). A node
made by the caller, or by a tag, may have no place (line None).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields

from .attributes import Attributes


@dataclass(eq=False, repr=False)
class Node:
    children: list = field(default_factory=list, kw_only=True)
    span: tuple = field(default=(0, 0), kw_only=True)       # offsets in the text given to parse (end excluded)
    line: int | None = field(default=None, kw_only=True)    # 1-based, of span[0]
    column: int | None = field(default=None, kw_only=True)

    @property
    def kind(self):
        return type(self).__name__

    def __post_init__(self):
        if isinstance(getattr(self, 'attributes', None), Mapping) \
                and not isinstance(self.attributes, Attributes):
            self.attributes = Attributes(self.attributes)    # a dict of the caller

    def __repr__(self):
        """Its fields, and the number of its children (not them: a tree may
        nest deeper than Python's recursion limit)."""
        shown = [f'{f.name}={getattr(self, f.name)!r}' for f in fields(self)
                 if f.repr and f.name != 'children']
        return f"{self.kind}({', '.join(shown)}, children=[{len(self.children)}])"

    def walk(self):
        """The node and its descendants, in document order (no recursion:
        a document may nest deeper than Python's recursion limit)."""
        stack = [self]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))


@dataclass(frozen=True)
class Written:
    """What the source wrote for a `name::` tag: what its Tag builds from.

    tag          the name written ('img', a macro; '' for a bare ::)
    text         the word glued after the groups (a URL, a variant), without
                 the final :: of `name::text::`
    inline       written `name::text::`: closed at once
    parentheses  classes and id as written (.a .b #c)
    brackets     style as written (for link::, its label)
    braces       HTML attributes as written
    label        the nodes of the label of a link (its [...]), else None
    line, column where it is; context: what a message quotes

    `attributes`: the HTML attributes it writes, a new Attributes - its
    classes and id, its style (not for a link: its [...] is its label),
    then its {...}."""
    tag: str = ''
    text: str = ''
    inline: bool = False
    parentheses: str = ''
    brackets: str = ''
    braces: str = ''
    label: list | None = None
    line: int | None = None
    column: int | None = None
    context: str = ''

    @property
    def attributes(self):
        from .export_html import element_attributes
        return element_attributes(self)


@dataclass(eq=False, repr=False)
class Document(Node):
    problems: list = field(default_factory=list)    # LHTMLWarning, with their line and column
    source: str = field(default='', repr=False)     # the text given to parse


@dataclass(eq=False, repr=False)
class Text(Node):
    value: str = ''                 # written as it is (LHTML escapes nothing)


@dataclass(eq=False, repr=False)
class Heading(Node):
    level: int = 1
    attributes: Attributes = field(default_factory=Attributes)
    written: str = ''               # its (.class #id) as written in the source (information)


@dataclass(eq=False, repr=False)
class List(Node):
    pass


@dataclass(eq=False, repr=False)
class Item(Node):
    pass


@dataclass(eq=False, repr=False)
class Strong(Node):
    pass


@dataclass(eq=False, repr=False)
class Emphasis(Node):
    pass


@dataclass(eq=False, repr=False)
class Element(Node):
    """An HTML element: <name attributes>children</name>.

    `void`: an element without content nor closing tag (<img>, <hr>).
    `end_tag`: False when its closing tag is not written (the source never
    closes it). `written`: what the source wrote, the Written its tag was
    given (None for an element of the caller): information on the source,
    render does not read it."""
    name: str
    attributes: Attributes = field(default_factory=Attributes)
    void: bool = False
    end_tag: bool = True
    written: Written | None = field(default=None, kw_only=True)


@dataclass(eq=False, repr=False)
class Video(Element):
    """<video attributes> with its sources: those the `media` resolver of
    render gives for `src`, or `src` itself."""
    name: str = 'video'
    src: str = ''


@dataclass(eq=False, repr=False)
class Code(Node):
    body: str = ''
    language: str = ''


@dataclass(eq=False, repr=False)
class InlineCode(Node):
    text: str = ''                  # as written between the backquotes


@dataclass(eq=False, repr=False)
class Math(Node):
    text: str = ''                  # with its \( \) or \[ \]
    display: bool = False


@dataclass(eq=False, repr=False)
class Raw(Node):
    """HTML written as it is: raw HTML of the source, a comment, a script, a
    style, Jinja, or HTML a tag gives."""
    text: str = ''
    raw_kind: str = 'html'          # html, comment, script, style, jinja
