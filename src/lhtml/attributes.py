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
from collections.abc import Iterable, MutableMapping
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
    comment as spaces (between attributes: {% if x %}alt="y"{% endif %}),
    unless it is glued to a name or an unquoted value (title=a{% if x %}b{%
    endif %}): a part of it; the placeholders as spaces."""
    parts, prev = [], 0
    for m in JINJA_RE.finditer(text):
        parts.append(text[prev:m.start()])
        before = parts[-1][-1:] if parts[-1] else (parts[-2][-1:] if len(parts) > 1 else '')
        glued = m.group(0).startswith('{{') or before == _PART or \
            (before and not before.isspace() and before not in '"\'')
        parts.append((_PART if glued else ' ') * len(m.group(0)))
        prev = m.end()
    parts.append(text[prev:])
    return PLACEHOLDER.sub(lambda m: ' ' * len(m.group(0)), ''.join(parts))


# The Jinja statements that open a block (closed by its end...): an
# attribute written in one depends on it
_BLOCKS = {'if', 'for', 'block', 'macro', 'call', 'filter', 'with', 'set', 'autoescape', 'raw', 'trans'}
_STATEMENT = re.compile(r'\{%[-+]?\s*(\w+)(.*?)[-+]?%\}', re.DOTALL)


def _depths(text):
    """(position, depth after it) at the end of each Jinja statement that
    opens or closes a block: the statements Jinja reads, not a {% in an
    expression's string ({{ '{% if %}' }}) or in a comment."""
    changes, depth = [], 0
    for zone in JINJA_RE.finditer(text):
        m = _STATEMENT.fullmatch(zone.group(0))
        if m is None:                   # an expression, a comment
            continue
        word = m.group(1)
        if word.startswith('end'):
            depth = max(0, depth - 1)
        elif word in _BLOCKS and not (word == 'set' and '=' in m.group(2)):
            depth += 1
        else:
            continue
        changes.append((zone.end(), depth))
    return changes


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
    nested: bool = False        # inside a Jinja block ({% if %}...{% endif %})

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
        self._items, self._names = [], {}   # its entries; how many there are of each name
        for name, value in (values or {}).items():
            self[name] = value

    def _append(self, entry):
        self._items.append(entry)
        if entry.name is not None:
            self._names[entry.name] = self._names.get(entry.name, 0) + 1

    def _replace(self, entries):
        self._items, self._names = [], {}
        for entry in entries:
            self._append(entry)

    @classmethod
    def read(cls, text: str | None) -> Attributes:
        """The attributes of an attribute text (`title="a" alt`)."""
        text = text or ''
        attributes, position = cls(), 0
        depths, k, depth = _depths(text), 0, 0
        for a in read(text):
            position = attributes._fragments(text, position, a.start)
            while k < len(depths) and depths[k][0] <= a.start:     # both in order: one walk
                depth = depths[k][1]
                k += 1
            attributes._append(_Entry(a.name, a.value, text[a.start:a.end],
                                      attributes._space(text, position, a.start), depth > 0))
            position = a.end
        attributes._fragments(text, position, len(text))
        return attributes

    def _space(self, text, start, end):
        """The spaces before an item as written; one before the first."""
        return text[start:end] if self._items else None

    def _fragments(self, text, start, end):
        """What is not an attribute: its pieces (a Jinja zone is one piece)."""
        for m in _FRAGMENT.finditer(text, start, end):
            self._append(_Entry(None, None, m.group(0), self._space(text, start, m.start())))
            start = m.end()
        return start

    def __getitem__(self, name):
        if isinstance(name, str) and (name := key(name)) in self._names:
            for entry in self._items:
                if entry.name == name:
                    return entry.value
        raise KeyError(name)

    def __setitem__(self, name, value):
        if not isinstance(name, str) or not (value is None or isinstance(value, str)):
            raise TypeError(f'an attribute is a str name and a str value or None, got {name!r}: {value!r}')
        name = key(name)
        if name not in self._names:
            self._append(_Entry(name, value))
            return
        found = next(entry for entry in self._items if entry.name == name)
        found.value, found.written = value, None    # in its place, written once
        if self._names[name] > 1:
            self._replace([entry for entry in self._items if entry.name != name or entry is found])

    def __delitem__(self, name):
        if name not in self:
            raise KeyError(name)
        self._replace(self.without({key(name)})._items)

    def __contains__(self, name):
        return isinstance(name, str) and key(name) in self._names

    def __iter__(self):
        return iter(dict.fromkeys(entry.name for entry in self._items if entry.name is not None))

    def __len__(self):
        return len(self._names)

    def __repr__(self):
        return f'Attributes({self.html().strip()!r})'

    def copy(self) -> Attributes:
        copied = Attributes()
        copied._replace(_Entry(e.name, e.value, e.written, e.space, e.nested) for e in self._items)
        return copied

    def without(self, names: Iterable[str], *, nested: bool = True) -> Attributes:
        """A copy without the attributes named in `names` (keys); the item
        after one removed takes its spaces (as if it was cut out of the
        text). `nested=False`: those written inside a Jinja block stay."""
        copied, space, cut = Attributes(), None, False
        for entry in self._items:
            if entry.name is not None and entry.name in names and (nested or not entry.nested):
                if not cut:
                    space, cut = entry.space, True
                continue
            entry = _Entry(entry.name, entry.value, entry.written, space if cut else entry.space, entry.nested)
            copied._append(entry)
            cut = False
        return copied

    def extend(self, other: Attributes) -> Attributes:
        """The attributes of `other` added after these, as they are."""
        for entry in other.copy()._items:
            self._append(entry)
        return self

    def values_of(self, name: str, *, nested: bool = True) -> list[str | None]:
        """Every value written for `name` (an attribute written twice);
        `nested=False`: not those written inside a Jinja block."""
        return [entry.value for entry in self._items if entry.name == key(name) and (nested or not entry.nested)]

    def html(self) -> str:
        """The attributes as HTML: ` name="value"` each."""
        return ''.join(entry.html() for entry in self._items)


# ---------------------------------------------------------------------------
# The attributes of an element: (.class #id) [style] {attributes}
# ---------------------------------------------------------------------------

def words(text, pattern=r'\S+'):
    """The matches of `pattern` in the text, a Jinja zone one piece of a
    word (.{{ c }}, a {{ b }})."""
    zones = []

    def hide(m):
        zones.append(m.group(0))
        return f'\x00{len(zones) - 1}\x00'
    show = lambda part: re.sub('\x00(\\d+)\x00', lambda m: zones[int(m.group(1))], part)
    return [show(word) for word in re.findall(pattern, JINJA_RE.sub(hide, text or ''))]


def classes_and_ids(text):
    """The classes and ids of '.class1 .class2 #id' (or '.class1.class2#id')."""
    classes, ids = [], []
    for token in words(text):
        if not token.startswith(('.', '#')):
            continue
        for part in words(token, r'[.#][^.#]+'):
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
    classes, ids = classes_and_ids(text)
    return assemble(classes, ids, '', Attributes())[0]


def assemble(classes, ids, style, rest, empty=()):
    """(class and id, style, the attributes left), as Attributes, from the
    classes and ids of (...), the style of [...] and the attributes `rest`
    (changed): the classes and styles of `rest` join those of (...) and
    [...] when both are given, or when `rest` gives one twice (the defaults
    of a macro, then the page); otherwise they stay where they are. An
    empty one is given too: (.a){class=""} is class="a", {class=""} alone
    class="" (and so when `empty` names it: written empty elsewhere). One
    written inside a Jinja block ({% if x %}class="a"{% endif %}) stays
    there. An id of `rest` replaces the one of (#id)."""
    head, styled = Attributes(), Attributes()
    written = rest.values_of('class', nested=False)     # one in a Jinja block stays there
    if written and (classes or len(written) > 1):
        classes = classes + [word for value in written if value for word in words(value)]
        rest = rest.without({'class'}, nested=False)
        head['class'] = ''
    written = rest.values_of('style', nested=False)
    if written and (style or len(written) > 1):
        style = join_styles(style, *(value for value in written if value))
        rest = rest.without({'style'}, nested=False)
        styled['style'] = ''
    for name, given in (('class', head), ('style', styled)):     # written empty elsewhere: given
        if name in empty and name not in given and not rest.values_of(name, nested=False):
            given[name] = ''
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
    classes, ids = classes_and_ids(written.parentheses)
    style = '' if written.tag == 'link' else written.brackets
    head, styled, rest = assemble(classes, ids, style, Attributes.read(written.braces))
    return head.extend(styled).extend(rest)
