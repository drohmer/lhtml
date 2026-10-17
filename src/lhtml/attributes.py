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
from collections.abc import MutableMapping
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


_FRAGMENT = re.compile(JINJA_RE.pattern + r'|\S+')


def quoted(value):
    """A value inside double quotes: its double quotes escaped (Jinja zones
    kept as written, they are rendered before the HTML)."""
    parts, prev = [], 0
    for m in JINJA_RE.finditer(value):
        parts.append(value[prev:m.start()].replace('"', '&quot;'))
        parts.append(m.group(0))
        prev = m.end()
    parts.append(value[prev:].replace('"', '&quot;'))
    return ''.join(parts)


class Attributes(MutableMapping):
    """The attributes of an element, in order: name -> value, a str as in
    HTML source (entities as written; a `"` in a value set here is written
    &quot;), or None for an attribute without value (`autoplay`). A name is
    read in any case. What sits among them and is not an attribute (a Jinja
    fragment: `{% if x %}alt="y"{% endif %}`) stays in its place.

    An attribute read from the source is written back as it was written
    (its quotes, the spaces before it) until it is set."""

    def __init__(self, values=None):
        # [name (lower case) or None, value, as written or None, the spaces before it or None: one]
        self._items = []
        for name, value in (values or {}).items():
            self[name] = value

    @classmethod
    def read(cls, text):
        """The attributes of an attribute text (`title="a" alt`)."""
        text = text or ''
        attributes, position = cls(), 0
        for a in read(text):
            position = attributes._fragments(text, position, a.start)
            attributes._items.append([a.name, a.value, text[a.start:a.end], attributes._space(text, position, a.start)])
            position = a.end
        position = attributes._fragments(text, position, len(text))
        if position < len(text):        # the spaces at its end
            attributes._items.append([None, None, '', text[position:]])
        return attributes

    def _space(self, text, start, end):
        space = text[start:end]
        return (' ' + space) if not self._items else space

    def _fragments(self, text, start, end):
        """What is not an attribute: its pieces (a Jinja zone is one piece)."""
        for m in _FRAGMENT.finditer(text, start, end):
            self._items.append([None, None, m.group(0), self._space(text, start, m.start())])
            start = m.end()
        return start

    def __getitem__(self, name):
        for item in self._items:
            if item[0] == name.lower():
                return item[1]
        raise KeyError(name)

    def __setitem__(self, name, value):
        key = name.lower()
        found = [item for item in self._items if item[0] == key]
        if found:
            found[0][1:3] = [value, None]
            self._items = [item for item in self._items if item[0] != key or item is found[0]]
        else:
            self._items.append([key, value, None, None])

    def __delitem__(self, name):
        key = name.lower()
        if key not in self:
            raise KeyError(name)
        self._items = [item for item in self._items if item[0] != key]

    def __contains__(self, name):
        return isinstance(name, str) and any(item[0] == name.lower() for item in self._items)

    def __iter__(self):
        seen = set()
        for item in self._items:
            if item[0] is not None and item[0] not in seen:
                seen.add(item[0])
                yield item[0]

    def __len__(self):
        return len(set(item[0] for item in self._items if item[0] is not None))

    def __repr__(self):
        return f'Attributes({self.html().strip()!r})'

    def extend(self, other):
        """The attributes of `other` added after these, as they are."""
        self._items += [list(item) for item in other._items]
        return self

    def values_of(self, name):
        """Every value written for `name` (an attribute written twice)."""
        return [item[1] for item in self._items if item[0] == name.lower()]

    def html(self):
        """The attributes as HTML: ` name="value"` each."""
        parts = []
        for name, value, written, space in self._items:
            if written is None:
                written = name if value is None else f'{name}="{quoted(value)}"'
            parts.append((' ' if space is None else space) + written)
        return ''.join(parts)
