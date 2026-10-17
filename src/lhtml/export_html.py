"""The tags: Tag, the built-in TAGS, and the attributes of an element.

A tag builds the nodes of an element from what the source wrote, the
element dict (tag_parser.extract_bracket_elements, then the parser):

    'tag'      the name written ('img'; '' for a bare ::)
    'text'     the word glued after the groups (a URL, a variant), without
               the final :: of `name::text::`
    'inline'   written `name::text::`: closed at once
    '()'       classes and id as written (.a .b #c)
    '[]'       style as written (for link::, its label as written)
    '{}'       HTML attributes as written
    'label'    the nodes of the label of a link (its [...]), else None
    'line', 'column', 'context'   where it is, what a message quotes
"""

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable

from .attributes import Attributes, names, without
from .nodes import Element, Node, Text, Video
from .patterns import JINJA_RE


# ---------------------------------------------------------------------------
# The attributes of an element
# ---------------------------------------------------------------------------

def _class_and_id(text):
    """The classes and ids of '.class1 .class2 #id' (or '.class1.class2#id')."""
    zones = []                          # a Jinja zone is one piece: .{{ c }}

    def hide(m):
        zones.append(m.group(0))
        return f'\x00{len(zones) - 1}\x00'
    show = lambda part: re.sub('\x00(\\d+)\x00', lambda m: zones[int(m.group(1))], part)
    classes, ids = [], []
    for token in JINJA_RE.sub(hide, text or '').split():
        if not token.startswith(('.', '#')):
            continue
        for part in re.findall(r'[.#][^.#]+', token):
            (classes if part[0] == '.' else ids).append(show(part[1:]))
    return classes, ids


def class_and_id(text):
    """The attributes class and id of '.class1 .class2 #id'."""
    return _parts(text, '', '')[0]


def _parts(class_id, style, written):
    """(class and id, style, the attributes written left), as Attributes:
    the classes and styles written {...} join those of (...) and [...] when
    both are given, or when {...} writes one twice (the defaults of a
    macro, then the page); otherwise they stay where they are written."""
    classes, ids = _class_and_id(class_id)
    rest = Attributes.read(written)
    values = [v for v in rest.values_of('class') if v]
    if values and (classes or len(rest.values_of('class')) > 1):
        for value in values:
            classes += [value] if JINJA_RE.search(value) else value.split()
        del rest['class']
    values = [v for v in rest.values_of('style') if v]
    if values and (style or len(rest.values_of('style')) > 1):
        for value in values:
            style = f'{style};{value}' if style and not style.rstrip().endswith(';') else style + value
        del rest['style']
    head = Attributes()
    if classes:
        head['class'] = ' '.join(dict.fromkeys(classes))
    if ids:
        head['id'] = ' '.join(ids)
    styled = Attributes({'style': style} if style else {})
    return head, styled, rest


def element_attributes(element, style=True):
    """The attributes of an element: its classes and id (.a #b), its style
    [...] (`style=False`: a link, whose [...] is its label), then those
    written {...}."""
    head, styled, rest = _parts(element['()'], element['[]'] if style else '', element['{}'])
    return head.extend(styled).extend(rest)


# ---------------------------------------------------------------------------
# The tags
# ---------------------------------------------------------------------------

@dataclass
class Tag:
    """A `name::` tag. `build(element)` gives its node (an Element, a Raw...)
    or a list of nodes, from the element dict (above); a container's is one
    Element, which holds what follows until its `::`. `container`: a bool,
    or a function of the element; written `name::text::`, it holds nothing
    either way. `url`: its text is a URL, kept as written (img::a__b.png)."""
    build: Callable
    container: bool | Callable = False
    url: bool = False

    def holds(self, element):
        if element['inline']:
            return False
        return self.container(element) if callable(self.container) else bool(self.container)


def generic(name):
    """div::, span::: holds what follows, unless written div::text::"""
    def build(element):
        node = Element(name=name, attributes=element_attributes(element))
        if element['text']:
            node.children.append(Text(value=element['text']))
        return node
    return Tag(build, container=True)


def _link(element):
    attributes = element_attributes(element, style=False)
    if 'href' not in attributes:
        attributes['href'] = element['text']
    return Element(name='a', attributes=attributes, children=list(element['label'] or []))


def _img(element):
    """<img src alt>: an alt or a src written replaces the default."""
    attributes = element_attributes(element)
    for name in ('src', 'alt'):
        if name not in attributes:
            attributes[name] = element['text']
    return Element(name='img', attributes=attributes, void=True)


def _video(defaults):
    def build(element):
        head, styled, rest = _parts(element['()'], element['[]'], element['{}'])
        given = Attributes.read(without(defaults, names(element['{}'])))
        return Video(attributes=rest.extend(given).extend(head).extend(styled), src=element['text'])
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

SPACER = Tag(lambda element: Element(name='div', attributes=Attributes({'style': 'height:1em;'})))     # ::nl


def node_list(built):
    """What a build gives, as a list of nodes."""
    nodes = built if isinstance(built, (list, tuple)) else [built]
    for node in nodes:
        if not isinstance(node, Node):
            raise TypeError(f'expected an lhtml node (Element, Text, Raw...), got {type(node).__name__}')
    return list(nodes)
