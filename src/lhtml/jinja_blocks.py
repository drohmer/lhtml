"""The Jinja blocks written among attributes ({% if x %}class="a"{% endif %}):
which ones there are, which hold an attribute, and how its values join the
others with their blocks (class="b {% if x %}a{% endif %}"). The entries are
those of Attributes: `name` (None for Jinja written alone), `written`,
`value`. Private to attributes.py: no rule here is a public one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .patterns import JINJA_RE

# The Jinja statements that open a block (closed by its end...): an
# attribute written in one depends on it
_BLOCKS = {'if', 'for', 'block', 'macro', 'call', 'filter', 'with', 'set', 'autoescape', 'raw', 'trans'}
# the statements of a block whose attributes join the others with it
# (blocks): those of the blocks that write what they hold where they are,
# holding no other statement (not a {% set %}: a value folded would be read
# before it, nor a {% macro %}, a {% block %}...)
_FOLDED = {word for block in ('if', 'for', 'with', 'filter', 'autoescape', 'raw')
           for word in (block, 'end' + block)} | {'elif', 'else'}
_TRIM = re.compile(r'^(\{%)[-+]|[-+](%\})$')       # whitespace control: {%- and -%}
_STATEMENT = re.compile(r'\{%[-+]?\s*(\w+)(.*?)[-+]?%\}', re.DOTALL)


def _kind(m):
    """'open', 'close' or 'branch' for a statement matched by _STATEMENT;
    None for one that is no part of a block ({% set x = 1 %})."""
    word = m.group(1)
    if word.startswith('end'):
        return 'close'
    if word in _BLOCKS and not (word == 'set' and '=' in m.group(2)):
        return 'open'
    return 'branch' if word in ('else', 'elif', 'empty') else None


def statement(written):
    """'open', 'close' or 'branch' ({% else %}...) for a Jinja statement
    that opens, closes or divides a block; None otherwise."""
    m = _STATEMENT.fullmatch(written or '')
    return None if m is None else _kind(m)


def depths(text):
    """(position, depth after it) at the end of each Jinja statement that
    opens or closes a block: the statements Jinja reads, not a {% in an
    expression's string ({{ '{% if %}' }}) or in a comment."""
    changes, depth = [], 0
    for zone in JINJA_RE.finditer(text):
        m = _STATEMENT.fullmatch(zone.group(0))
        kind = None if m is None else _kind(m)      # an expression, a comment: None
        if kind == 'close':
            depth = max(0, depth - 1)
        elif kind == 'open':
            depth += 1
        else:
            continue
        changes.append((zone.end(), depth))
    return changes


def _words(block):
    """The statements of a block, by their word (if, endif, set...)."""
    return [m.group(1) for e in block if e.name is None for m in [_STATEMENT.fullmatch(e.written or '')] if m]


def blocks(entries, name):
    """The blocks written among `entries` (from the opening statement to
    its closing one) that hold an attribute `name` and write what they hold
    where they are: {% if %}, {% for %}, {% with %}, {% filter %},
    {% autoescape %}, {% raw %}; their entries. Not the others, nor one that
    holds another statement: what a {% set %}, a {% macro %} or a
    {% block %} holds is not written there as it is, and a value folded
    would be read before its {% set %}."""
    found, block, depth = [], [], 0
    for entry in entries:
        kind = statement(entry.written) if entry.name is None else None
        if kind == 'open':
            depth += 1
        if depth:
            block.append(entry)
        if kind == 'close' and depth:
            depth -= 1
            if depth == 0:
                if all(word in _FOLDED for word in _words(block)) and any(e.name == name for e in block):
                    found.append(block)
                block = []
    return found


@dataclass
class _Opened:
    """A block opened while one is folded: its statement's word, whether a
    value may be written before it, whether one is written in it."""
    word: str
    value_before: bool
    value_in: bool = False


def fold(block, name, joiner):
    """The values of `name` in a block, with its statements, as one value:
    a joiner before a value when one may be written before it - in the
    block before it (not in another branch), or a turn of a loop. The
    whitespace control of a statement ({%- -%}) is dropped: it would take
    the joiners."""
    folded, value_before, opened, loops = [], False, [], 0     # loops: the {% for %} open
    for entry in block:
        kind = statement(entry.written) if entry.name is None else None
        if kind:
            folded.append(_TRIM.sub(r'\1\2', entry.written))
            if kind == 'open':
                opened.append(_Opened(_STATEMENT.fullmatch(entry.written).group(1), value_before))
                loops += opened[-1].word == 'for'
            elif kind == 'branch':
                value_before = opened[-1].value_before
            elif kind == 'close':
                level = opened.pop()
                loops -= level.word == 'for'
                value_before = level.value_before or level.value_in
                if opened:              # a value in it is one in the block around it
                    opened[-1].value_in = opened[-1].value_in or level.value_in
        elif entry.name == name and entry.value:
            folded.append((joiner if value_before or loops else '') + entry.value)
            value_before = True
            if opened:
                opened[-1].value_in = True
    return ''.join(folded)


def entries_in(name, found):
    """The ids of the entries `name` of the blocks `found`, and of the whole
    block when it holds nothing else but its statements."""
    dropped = set()
    for block in found:
        kept = [e for e in block if e.name != name and not (e.name is None and statement(e.written))]
        dropped.update(id(e) for e in (block if not kept else [e for e in block if e.name == name]))
    return dropped
