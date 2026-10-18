"""The nodes of the document tree (lhtml.parse gives it, lhtml.render
writes its HTML from these fields alone: change a node, the HTML changes).

Every node has its `children`, and its place in the text given to parse:
`span`, the offsets of its source, `line` and `column` (1-based) of its
start. They are keyword arguments, so a node is made as it reads:
Text('Hello'), Element('div', {'class': 'note'}, children=[...]). A node
made by the caller, or by a tag, may have no place (line None).
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, fields

from .attributes import Attributes, element_attributes

_ELEMENT_NAME = re.compile(r'[A-Za-z][\w:.-]*')


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
        name = getattr(self, 'name', None)
        if name is not None and not (isinstance(name, str) and _ELEMENT_NAME.fullmatch(name)):
            raise ValueError(f'{self.kind}: invalid element name {name!r} (a letter, then letters, digits, '
                             f'-, _, : or .)')
        if not hasattr(self, 'attributes') or isinstance(self.attributes, Attributes):
            return
        if self.attributes is None:
            self.attributes = Attributes()
        elif isinstance(self.attributes, Mapping):
            self.attributes = Attributes(self.attributes)    # a dict of the caller
        else:
            raise TypeError(f'{self.kind}: attributes must be a mapping or lhtml.Attributes, '
                            f'got {type(self.attributes).__name__}')

    def __repr__(self):
        """Its fields, and the number of its children (not them: a tree may
        nest deeper than Python's recursion limit)."""
        shown = [f'{f.name}={getattr(self, f.name)!r}' for f in fields(self)
                 if f.repr and f.name != 'children']
        return f"{self.kind}({', '.join(shown)}, children=[{len(self.children)}])"

    def walk(self) -> Iterator[Node]:
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
    label        the nodes of the label of a link (its [...]), a tuple, else
                 None: the link's children (the same nodes)
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
    label: tuple | None = field(default=None, compare=False)
    line: int | None = None
    column: int | None = None
    context: str = ''

    @property
    def attributes(self):
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
    attributes: Attributes | Mapping[str, str | None] = field(default_factory=Attributes)    # a dict: made one
    parentheses: str = ''           # its (.class #id) as written in the source (information)


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
    `end_tag`: False when its closing tag is not written (an element still
    open at the end of the document; one the end of a heading, an item, a
    bold or an italic closes gets its closing tag). `written`: what the
    source wrote, the Written its tag was given (None for an element the
    caller made, or one a tag made inside the nodes it returns):
    information on the source, render does not read it."""
    name: str
    attributes: Attributes | Mapping[str, str | None] = field(default_factory=Attributes)    # a dict: made one
    void: bool = False
    end_tag: bool = True
    written: Written | None = field(default=None, kw_only=True)


@dataclass(eq=False, repr=False)
class Video(Element):
    """<video attributes> with its sources: those the `media` resolver of
    render gives for `src`, or `src` itself: Video('clip.mp4')."""
    name: str = field(default='video', kw_only=True)
    attributes: Attributes | Mapping[str, str | None] = field(default_factory=Attributes, kw_only=True)
    void: bool = field(default=False, kw_only=True)
    end_tag: bool = field(default=True, kw_only=True)
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
