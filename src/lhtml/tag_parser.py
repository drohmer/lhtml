"""The parser of a tag element: the name before `::` and what follows it.

    tag::(.class #id)[style]{attrs}text

After `::` come, in any order, bracket groups - `(...)` classes and id,
`[...]` style, `{...}` HTML attributes, each nesting its own kind of
bracket - and a word, the text (a URL, a variant, ...). The element ends at
whitespace, at `<`, at a node of the document tree (EVENT_CHAR: the end of
a bold, a heading...), at a protected zone, or at text that follows a group that itself followed text
(`link::url[label]rest`). A protected URL (placeholder of kind U) is text.
"""

import bisect
import functools
import re

from .errors import LHTMLParseError
from .patterns import EVENT_CHAR

PAIRS = {'(': ')', '[': ']', '{': '}'}
_TAG_NAME_BEFORE = re.compile(r'[A-Za-z][A-Za-z0-9_-]*\Z')
_MAX_TAG_NAME = 64


class _Quotes:
    """Where the quotes, line ends and blank lines of a text are: the end of
    a quoted string found by bisection, so that a text full of unclosed
    quotes is still read in one pass."""

    def __init__(self, text):
        self.at = {q: [m.start() for m in re.finditer(q, text)] for q in '"\''}
        self.lines = [m.start() for m in re.finditer('\n', text)]
        self.blanks = [m.start() for m in re.finditer(r'\n[ \t]*\n', text)]

    def closing(self, quote, start, across_lines):
        """The quote that closes the one at `start`, before the end of its
        line (or of its paragraph: `across_lines`); None if there is none."""
        positions = self.at[quote]
        k = bisect.bisect_right(positions, start)
        if k == len(positions):
            return None
        limits = self.blanks if across_lines else self.lines
        n = bisect.bisect_right(limits, start)
        return positions[k] if n == len(limits) or positions[k] < limits[n] else None


_VALUE_BEFORE = re.compile(r'=[ \t]*\Z')          # {title="..."}
_CSS_STRING_BEFORE = re.compile(r'[:(,][ \t]*\Z')     # [content:"]"], [font-family:'A', 'B']


@functools.lru_cache(maxsize=8)
def _matches(text):
    """The closing bracket of each opening one, by position, each kind of
    bracket nesting its own kind only (an unclosed one has none): computed
    once per text, so that unclosed brackets do not each scan to its end.

    A quoted string holds its brackets, as in HTML and CSS: in a {...}, a
    value quoted after its `=` and closed before the end of its paragraph
    ({title="a } b"}); in a [...], a CSS string after `:`, `(` or `,` and
    closed on its line ([content:"]"]). An apostrophe elsewhere is text
    (l'eau)."""
    matches, stacks = {}, {ch: [] for ch in PAIRS}
    closing = {close: ch for ch, close in PAIRS.items()}
    quotes = None
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in '"\'' and (stacks['{'] or stacks['[']):
            inner = max((k for k in ('{', '[') if stacks[k]), key=lambda k: stacks[k][-1])
            before = text[max(0, i - 64):i]
            if (_VALUE_BEFORE if inner == '{' else _CSS_STRING_BEFORE).search(before):
                quotes = quotes or _Quotes(text)
                end = quotes.closing(ch, i, across_lines=inner == '{')
                if end is not None:
                    i = end + 1
                    continue
        if ch in PAIRS:
            stacks[ch].append(i)
        elif ch in closing and stacks[closing[ch]]:
            matches[stacks[closing[ch]].pop()] = i
        i += 1
    return matches


def extract_bracket_elements(text, index_start):
    """The element whose `::` ends at `index_start`, as a dict:

    '()', '[]', '{}'   the content of the groups (a group written twice is
                       joined with a space)
    'text'             the word after `::`
    'groups'           (kind, start, end) of each group: its content is
                       text[start:end]
    'tag'              the name before `::` ('' for a bare `::`)
    'index_start'      where the name starts
    'index_end'        where the element ends

    A closing bracket without its opening one makes the whole element text
    (its groups are still listed, so that their content stays literal).
    An unclosed bracket raises LHTMLParseError."""
    element = {'[]': '', '()': '', '{}': '', 'text': '', 'groups': [],
               'tag': '', 'index_start': index_start, 'index_end': index_start}
    if index_start >= 2:
        name_end = index_start - 2
        m = _TAG_NAME_BEFORE.search(text, max(0, name_end - _MAX_TAG_NAME), name_end)
        tag_start = m.start() if m else name_end
        element['tag'] = text[tag_start:name_end]
        element['index_start'] = tag_start

    word, groups = [], []
    seen_text = group_after_text = stray = False
    i = index_start
    while i < len(text):
        ch = text[i]
        if ch == '\x00' and text[i + 1:i + 2] == 'U':       # a protected URL
            end = text.find('\x00', i + 1)
            if end > i:
                word.append(text[i:end + 1])
                seen_text = True
                i = end + 1
                continue
        if ch.isspace() or ch == '\x00' or ch == '<' or ch == EVENT_CHAR:
            break
        if ch in PAIRS:
            close = PAIRS[ch]
            j = _matches(text).get(i)
            if j is None:
                raise LHTMLParseError(f'Unclosed bracket {ch!r} (expected {close!r})')
            j += 1
            groups.append((ch + close, i + 1, j - 1))
            group_after_text = group_after_text or seen_text
            i = j
            continue
        if group_after_text:
            break
        stray = stray or ch in ')]}'
        word.append(ch)
        seen_text = True
        i += 1

    element['index_end'] = i
    element['groups'] = groups  # protected from formatting even in a stray element
    if stray:                   # not a tag element: all of it is text
        element['stray'] = bool(groups)
        element['text'] = text[index_start:i]
        return element
    element['text'] = ''.join(word)
    for kind, start, end in groups:
        element[kind] += (' ' if element[kind] else '') + text[start:end]
    return element
