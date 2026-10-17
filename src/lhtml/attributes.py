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


_PART = '\x01'                     # a Jinja expression, part of a name or a value


def _masked(text):
    """The text with its Jinja at its place: an expression as a part of a
    name or a value (data-{{ k }}="v", title={{ x }}), a statement or a
    comment as spaces (between attributes: {% if x %}alt="y"{% endif %});
    the placeholders as spaces."""
    def mask(m):
        return (_PART if m.group(0).startswith('{{') else ' ') * len(m.group(0))
    return PLACEHOLDER.sub(lambda m: ' ' * len(m.group(0)), JINJA_RE.sub(mask, text))


def key(name):
    """The name an attribute is known by: lower case, its Jinja as written
    (data-{{ K }} is not data-{{ k }})."""
    parts, prev = [], 0
    for m in JINJA_RE.finditer(name):
        parts += [name[prev:m.start()].lower(), m.group(0)]
        prev = m.end()
    return ''.join(parts) + name[prev:].lower()


def read(text):
    """The attributes of an attribute text, in order."""
    text = text or ''
    attributes = []
    for m in _ATTRIBUTE.finditer(_masked(text)):
        if m.group(2) is None and not m.group(1).strip(_PART):
            continue                    # {{ attributes }}: a fragment, not a name
        value = None
        if m.group(2) is not None:
            value = text[m.start(2):m.end(2)]
            if value[:1] in '"\'' and len(value) >= 2:
                value = value[1:-1]
        attributes.append(Attribute(key(text[m.start(1):m.end(1)]), m.start(), m.end(), value))
    return attributes


def unclosed(text):
    """Whether a value quoted after its = has no closing quote (title="a)."""
    masked = _masked(text or '')
    position = 0
    while (m := re.compile(r'=[ \t]*(["\'])').search(masked, position)):
        end = masked.find(m.group(1), m.end())
        if end == -1:
            return True
        position = end + 1
    return False


def layered(*layers):
    """Attributes, the first ones the defaults: a copy of each, without the
    attributes a later one gives (class and style add up: kept)."""
    result, given = [], set()
    for layer in reversed(layers):
        result.append(layer.without(given - set(ADDED)))
        given |= set(layer)
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


@dataclass(slots=True)
class _Entry:
    """An item of Attributes: an attribute (`name`, its key), or a fragment
    among them (name None: a Jinja zone). `written`: as the source wrote it
    (None once set: written from name and value); `space`: the spaces
    before it as written (None: one)."""
    name: str | None
    value: str | None = None
    written: str | None = None
    space: str | None = None

    def html(self):
        written = self.written
        if written is None:
            written = self.name if self.value is None else f'{self.name}="{quoted(self.value)}"'
        return (' ' if self.space is None else self.space) + written


class Attributes(MutableMapping):
    """The attributes of an element, in order: name -> value, a str as in
    HTML source (entities as written; a `"` in a value set here is written
    &quot;), or None for an attribute without value (`autoplay`). A name is
    read in any case, its Jinja as written (key). What sits among them and
    is not an attribute (a Jinja fragment: `{% if x %}alt="y"{% endif %}`)
    stays in its place.

    An attribute read from the source is written back as it was written
    (its quotes, the spaces before it) until it is set."""

    def __init__(self, values=None):
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
            attributes._items.append(_Entry(a.name, a.value, text[a.start:a.end],
                                            attributes._space(text, position, a.start)))
            position = a.end
        attributes._fragments(text, position, len(text))
        return attributes

    def _space(self, text, start, end):
        """The spaces before an item as written; one before the first."""
        return text[start:end] if self._items else None

    def _fragments(self, text, start, end):
        """What is not an attribute: its pieces (a Jinja zone is one piece)."""
        for m in _FRAGMENT.finditer(text, start, end):
            self._items.append(_Entry(None, None, m.group(0), self._space(text, start, m.start())))
            start = m.end()
        return start

    def __getitem__(self, name):
        if isinstance(name, str):
            name = key(name)
            for entry in self._items:
                if entry.name == name:
                    return entry.value
        raise KeyError(name)

    def __setitem__(self, name, value):
        if not isinstance(name, str) or not (value is None or isinstance(value, str)):
            raise TypeError(f'an attribute is a str name and a str value or None, got {name!r}: {value!r}')
        name = key(name)
        found = next((entry for entry in self._items if entry.name == name), None)
        if found is None:
            self._items.append(_Entry(name, value))
        else:                           # in its place, written once
            found.value, found.written = value, None
            self._items = [entry for entry in self._items if entry.name != name or entry is found]

    def __delitem__(self, name):
        if name not in self:
            raise KeyError(name)
        self._items = self.without({key(name)})._items

    def __contains__(self, name):
        return isinstance(name, str) and any(entry.name == key(name) for entry in self._items)

    def __iter__(self):
        return iter(dict.fromkeys(entry.name for entry in self._items if entry.name is not None))

    def __len__(self):
        return len(set(entry.name for entry in self._items if entry.name is not None))

    def __repr__(self):
        return f'Attributes({self.html().strip()!r})'

    def copy(self):
        copied = Attributes()
        copied._items = [_Entry(e.name, e.value, e.written, e.space) for e in self._items]
        return copied

    def without(self, names):
        """A copy without the attributes named in `names` (keys); the item
        after one removed takes its spaces (as if it was cut out of the
        text)."""
        copied, space, cut = Attributes(), None, False
        for entry in self._items:
            if entry.name is not None and entry.name in names:
                if not cut:
                    space, cut = entry.space, True
                continue
            entry = _Entry(entry.name, entry.value, entry.written, space if cut else entry.space)
            copied._items.append(entry)
            cut = False
        return copied

    def extend(self, other):
        """The attributes of `other` added after these, as they are."""
        self._items += other.copy()._items
        return self

    def values_of(self, name):
        """Every value written for `name` (an attribute written twice)."""
        return [entry.value for entry in self._items if entry.name == key(name)]

    def html(self):
        """The attributes as HTML: ` name="value"` each."""
        return ''.join(entry.html() for entry in self._items)
