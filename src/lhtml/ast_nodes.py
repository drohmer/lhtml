"""AST node definitions for LHTML.

These dataclasses represent the intermediate representation produced
by the LHTML parser before HTML emission. Each node corresponds to
an LHTML language construct as defined in grammar.ebnf.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Union


# Type alias for any LHTML node
LHTMLNode = Union[
    'TextNode', 'TagElement', 'HeadingNode', 'ListNode',
    'InlineFormat', 'CodeBlock', 'VerbatimBlock',
    'IncludeDirective', 'Comment', 'SpacerNode', 'ClosingTag'
]


@dataclass
class LHTMLDocument:
    """Root node representing a full LHTML document."""
    meta: dict = field(default_factory=dict)
    children: list[LHTMLNode] = field(default_factory=list)


@dataclass
class TextNode:
    """Passthrough text (raw HTML, Jinja2 templates, prose).
    Not transformed by LHTML — emitted as-is."""
    content: str
    source_span: tuple[int, int] = (0, 0)


@dataclass
class TagElement:
    """An LHTML tag element: tag::(.class #id)[style]{attrs} content ::

    For special tags (link, img, video), the 'text' field holds the
    URL or file path that appears between :: and the first bracket.
    """
    tag: str                        # "div", "span", "link", "img", "video", "videoplay", ""
    classes: list[str] = field(default_factory=list)
    id: str | None = None
    style: str = ''
    inline_attrs: str = ''
    text: str = ''                  # URL for link, path for img/video, content for self-closing
    self_closing: bool = False      # True if content ends with ::
    source_span: tuple[int, int] = (0, 0)


@dataclass
class HeadingNode:
    """A heading: =() Title, ==() Subtitle, etc."""
    level: int                      # 1-6
    text: str = ''
    classes: list[str] = field(default_factory=list)
    id: str | None = None
    source_span: tuple[int, int] = (0, 0)


@dataclass
class ListItem:
    """A single list item with its nesting level."""
    level: int                      # 1 for *, 2 for **, etc.
    content: str = ''


@dataclass
class ListNode:
    """A sequence of list items (* item, ** subitem)."""
    items: list[ListItem] = field(default_factory=list)
    source_span: tuple[int, int] = (0, 0)


@dataclass
class InlineFormat:
    """Inline formatting: **bold**, __italic__, `code`."""
    kind: str                       # "bold" | "italic" | "code"
    content: str = ''
    source_span: tuple[int, int] = (0, 0)


@dataclass
class CodeBlock:
    """A code block: code::[language] ... code::[-]."""
    language: str = ''
    content: str = ''
    source_span: tuple[int, int] = (0, 0)


@dataclass
class VerbatimBlock:
    """A verbatim block: verbatim::[] ... verbatim::[-].
    Content is preserved without any LHTML processing."""
    content: str = ''
    source_span: tuple[int, int] = (0, 0)


@dataclass
class IncludeDirective:
    """An include directive: include::filename."""
    filename: str = ''
    source_span: tuple[int, int] = (0, 0)


@dataclass
class Comment:
    """An LHTML comment: ::#comment text."""
    text: str = ''
    source_span: tuple[int, int] = (0, 0)


@dataclass
class SpacerNode:
    """A spacer element: ::nl."""
    source_span: tuple[int, int] = (0, 0)


@dataclass
class ClosingTag:
    """A bare closing tag: :: (closes the most recent open tag)."""
    source_span: tuple[int, int] = (0, 0)
