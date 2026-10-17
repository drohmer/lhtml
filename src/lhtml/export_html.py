"""The tags: Tag, the built-in TAGS, and the attributes of an element.

A tag builds the nodes of an element from what the source wrote, a
Written (nodes.py): its name, its groups as written, the word after them.
"""

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable

from .attributes import Attributes
from .nodes import Element, Node, Text, Video
from .patterns import JINJA_RE


# ---------------------------------------------------------------------------
# The attributes of an element
# ---------------------------------------------------------------------------

def _words(text, pattern=r'\S+'):
    """The matches of `pattern` in the text, a Jinja zone one piece of a
    word (.{{ c }}, a {{ b }})."""
    zones = []

    def hide(m):
        zones.append(m.group(0))
        return f'\x00{len(zones) - 1}\x00'
    show = lambda part: re.sub('\x00(\\d+)\x00', lambda m: zones[int(m.group(1))], part)
    return [show(word) for word in re.findall(pattern, JINJA_RE.sub(hide, text or ''))]


def _class_and_id(text):
    """The classes and ids of '.class1 .class2 #id' (or '.class1.class2#id')."""
    classes, ids = [], []
    for token in _words(text):
        if not token.startswith(('.', '#')):
            continue
        for part in _words(token, r'[.#][^.#]+'):
            (classes if part[0] == '.' else ids).append(part[1:])
    return classes, ids


def join_styles(*styles):
    """Styles one after the other, a `;` between them."""
    joined = ''
    for style in styles:
        if style:
            joined = f'{joined};{style}' if joined and not joined.rstrip().endswith(';') else joined + style
    return joined


def class_and_id(text):
    """The attributes class and id of '.class1 .class2 #id'."""
    classes, ids = _class_and_id(text)
    return assemble(classes, ids, '', Attributes())[0]


def assemble(classes, ids, style, rest):
    """(class and id, style, the attributes left), as Attributes, from the
    classes and ids of (...), the style of [...] and the attributes `rest`
    (changed): the classes and styles of `rest` join those of (...) and
    [...] when both are given, or when `rest` gives one twice (the defaults
    of a macro, then the page); otherwise they stay where they are. An
    empty one is given too: (.a){class=""} is class="a", {class=""} alone
    class="". An id of `rest` replaces the one of (#id)."""
    head, styled = Attributes(), Attributes()
    written = rest.values_of('class')
    if written and (classes or len(written) > 1):
        classes = classes + [word for value in written if value for word in _words(value)]
        del rest['class']
        head['class'] = ''
    written = rest.values_of('style')
    if written and (style or len(written) > 1):
        style = join_styles(style, *(value for value in written if value))
        del rest['style']
        styled['style'] = ''
    if classes:
        head['class'] = ' '.join(dict.fromkeys(classes))
    if ids and 'id' not in rest:
        head['id'] = ' '.join(ids)
    if style:
        styled['style'] = style
    return head, styled, rest


def element_attributes(written):
    """The attributes of a Written: its classes and id (.a #b), its style
    [...] (not for link::, whose [...] is its label), then those written
    {...}."""
    classes, ids = _class_and_id(written.parentheses)
    style = '' if written.tag == 'link' else written.brackets
    head, styled, rest = assemble(classes, ids, style, Attributes.read(written.braces))
    return head.extend(styled).extend(rest)


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
    build: Callable
    container: bool | Callable = False
    url: bool = False

    def holds(self, written):
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
    return Element('a', attributes, children=list(written.label or []))


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
        classes, ids = _class_and_id(written.parentheses)
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
