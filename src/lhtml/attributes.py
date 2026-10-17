"""The attributes of a group {...}, of a macro (attrs) or of a tag: one
reader for all of them, and one rule when several give the same attribute.

The reader knows the names, the values (quoted or not) and their places in
the text, nothing else: a value is never parsed (CSS, JavaScript) nor
rewritten, and Jinja is opaque (`{% if x %}alt="y"{% endif %}` writes alt).

When several give an attribute, the later one replaces it, in this order:

    the defaults of the tag (img: src, alt; link: href; videoplay: autoplay...)
    the attributes of the macro (attrs)
    its url argument (demo::page.html with url: src)
    the attributes written in the page {...}

except class and style, which add up: the classes once each, in this order
after those of (.a .b), the styles after the one of [...].
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .patterns import JINJA_RE, PLACEHOLDER

# A name, then its value: quoted, or unquoted up to the next space (`a=b=c`
# is one attribute). No leading \s*: finditer skips what is not a name.
_ATTRIBUTE = re.compile(r'([^\s"\'=<>/{}%]+)(?:[ \t]*=[ \t]*("[^"]*"|\'[^\']*\'|[^\s"\'`]+))?')
ADDED = ('class', 'style')          # these add up, the others are replaced


@dataclass(frozen=True)
class Attribute:
    name: str           # lower case
    start: int          # its place in the text
    end: int
    value: str | None   # as written, without its quotes (None: no value)


def _masked(text):
    """The text with its Jinja and placeholders as spaces, at their place."""
    blank = lambda m: ' ' * len(m.group(0))
    return PLACEHOLDER.sub(blank, JINJA_RE.sub(blank, text))


def read(text):
    """The attributes of an attribute text, in order."""
    text = text or ''
    attributes = []
    for m in _ATTRIBUTE.finditer(_masked(text)):
        value = None
        if m.group(2) is not None:
            value = text[m.start(2):m.end(2)]
            if value[:1] in '"\'' and len(value) >= 2:
                value = value[1:-1]
        attributes.append(Attribute(m.group(1).lower(), m.start(), m.end(), value))
    return attributes


def names(text):
    """The names written in an attribute text, lower case."""
    return {a.name for a in read(text)}


def without(text, removed):
    """The text without the attributes named in `removed`; the rest kept
    as written, spaces in values included."""
    text = text or ''
    cuts = [a for a in read(text) if a.name in removed]
    for a in reversed(cuts):
        end = a.end
        while end < len(text) and text[end] in ' \t\n':
            end += 1
        text = text[:a.start] + text[end:]
    return text.strip() if cuts else text


def join(*parts):
    """Attribute texts side by side."""
    return ' '.join(p for p in parts if p)


def layered(*layers):
    """The attribute texts of `layers`, the first ones the defaults: an
    attribute a later layer writes is removed from the earlier ones (class
    and style add up). The texts stay in the order given."""
    result, written = [], set()
    for layer in reversed(layers):
        result.append(without(layer, written - set(ADDED)))
        written |= names(layer)
    return list(reversed(result))


def take(text, name):
    """(the values of the attribute `name` in the text, the text without it)."""
    values = [a.value for a in read(text) if a.name == name and a.value]
    return values, without(text, {name}) if values else text
