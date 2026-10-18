"""The tags: Tag and the built-in TAGS (the attributes they write: attributes.py).

A tag builds the nodes of an element from what the source wrote, a
Written (nodes.py): its name, its groups as written, the word after them.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from collections.abc import Callable

from .attributes import Attributes, assemble, classes_and_ids
from .nodes import Element, Node, Text, Video, Written


# ---------------------------------------------------------------------------
# The tags
# ---------------------------------------------------------------------------

@dataclass
class Tag:
    """A `name::` tag. `build(written)` gives its node (an Element, a Raw
    for HTML as it is...) or a list of nodes, from what the source wrote (a
    Written); a container's is one Element, and the parser puts in it what
    follows until its `::`. `container`: a bool, or a function of the
    Written; written `name::text::`, it holds nothing either way. `url`:
    its text is a URL, kept as written (img::a__b.png)."""
    build: Callable[[Written], Node | list[Node]]
    container: bool | Callable[[Written], bool] = False
    url: bool = False

    def holds(self, written: Written) -> bool:
        if written.inline:
            return False
        return self.container(written) if callable(self.container) else bool(self.container)


def generic(name):
    """div::, span::: holds what follows, unless written div::text::"""
    def build(written):
        node = Element(name, written.attributes)
        if written.text:
            node.children.append(Text(written.text))
        return node
    return Tag(build, container=True)


def _link(written):
    attributes = written.attributes
    if 'href' not in attributes:
        attributes['href'] = written.text
    label = list(written.label or []) or [Text(written.text)]     # no label: its URL shows
    return Element('a', attributes, children=label)


def _img(written):
    """<img src alt>: an alt or a src written replaces the default."""
    attributes = written.attributes
    for name in ('src', 'alt'):
        if name not in attributes:
            attributes[name] = written.text
    return Element('img', attributes, void=True)


def _video(defaults):
    defaults = Attributes.read(defaults)

    def build(written):
        page = Attributes.read(written.braces)
        given = defaults.without(set(page))
        classes, ids = classes_and_ids(written.parentheses)
        head, styled, rest = assemble(classes, ids, written.brackets, page)
        return Video(attributes=rest.extend(given).extend(head).extend(styled), src=written.text)
    return build


# Read-only: a run adds its own tags with run(..., tags=)
TAGS = MappingProxyType({
    'div': generic('div'),
    'span': generic('span'),
    'link': Tag(_link, url=True),
    'img': Tag(_img, url=True),
    'video': Tag(_video(''), url=True),
    'videoplay': Tag(_video('autoplay loop muted playsinline'), url=True),
})

SPACER = Tag(lambda written: Element('div', {'style': 'height:1em;'}))     # ::nl


def node_list(built):
    """What a build gives, as a list of nodes."""
    nodes = built if isinstance(built, (list, tuple)) else [built]
    for node in nodes:
        if not isinstance(node, Node):
            raise TypeError(f'expected an lhtml node (Element, Text, Raw...), got {type(node).__name__}')
    return list(nodes)
