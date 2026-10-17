"""The parser of a tag element: the name before `::` and what follows it.

    tag::(.class #id)[style]{attrs}text

After `::` come, in any order, bracket groups - `(...)` classes and id,
`[...]` style, `{...}` HTML attributes, each nesting its own kind of
bracket - and a word, the text (a URL, a variant, ...). The element ends at
whitespace, at `<`, at a node of the document tree (EVENT_CHAR: the end of
a bold, a heading...), at a protected zone, or at text that follows a group that itself followed text
(`link::url[label]rest`). A protected URL (placeholder of kind U) is text.
"""

import functools
import re

from .errors import LHTMLParseError
from .patterns import EVENT_CHAR

PAIRS = {'(': ')', '[': ']', '{': '}'}
_TAG_NAME_BEFORE = re.compile(r'[A-Za-z][A-Za-z0-9_-]*\Z')
_MAX_TAG_NAME = 64


@functools.lru_cache(maxsize=8)
def _matches(text):
    """The closing bracket of each opening one, by position, each kind of
    bracket nesting its own kind only (an unclosed one has none): computed
    once per text, so that unclosed brackets do not each scan to its end.
    In an attribute group {...}, a quoted value closed on its line is opaque:
    {title="a } b"} holds the brace."""
    matches, stacks = {}, {ch: [] for ch in PAIRS}
    closing = {close: ch for ch, close in PAIRS.items()}
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in '"\'' and stacks['{']:
            end = text.find(ch, i + 1)
            if end != -1 and '\n' not in text[i:end]:
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
        element['text'] = text[index_start:i]
        return element
    element['text'] = ''.join(word)
    for kind, start, end in groups:
        element[kind] += (' ' if element[kind] else '') + text[start:end]
    return element
