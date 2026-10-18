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
from dataclasses import dataclass, field

from .errors import LHTMLParseError, warn
from .patterns import EVENT_CHAR, PLACEHOLDER_CHAR, SPACER

PAIRS = {'(': ')', '[': ']', '{': '}'}
_TAG_NAME_BEFORE = re.compile(r'[A-Za-z][A-Za-z0-9_-]*\Z')
_MAX_TAG_NAME = 64


def tag_name_before(text, end):
    """The tag name written just before `end` (a ::), '' if none."""
    found = _TAG_NAME_BEFORE.search(text, max(0, end - _MAX_TAG_NAME), end)
    return found.group() if found else ''


class _Quotes:
    """Where the quotes, line ends and blank lines of a text are: the end of
    a quoted string found by bisection, so that a text full of unclosed
    quotes is still read in one pass."""

    def __init__(self, text):
        self.at = {q: [m.start() for m in re.finditer(q, text)] for q in '"\''}
        self.lines = [m.start() for m in re.finditer('\n', text)]
        self.blanks = [m.start() for m in re.finditer(r'\n[ \t]*\n', text)]

    def same_paragraph(self, start, end):
        """Whether no blank line lies between two positions."""
        return bisect.bisect_right(self.blanks, start) == bisect.bisect_right(self.blanks, end)

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


_VALUE_BEFORE = re.compile(r'[^\s"\'=<>/{}]=[ \t]*\Z')     # {title="..."}: a name, then its =
_CSS_STRING_BEFORE = re.compile(r'[:(,][ \t]*\Z')     # [content:"]"], [font-family:'A', 'B']


@functools.lru_cache(maxsize=8)
def _matches(text):
    """The closing bracket of each opening one, by position, each kind of
    bracket nesting its own kind only (an unclosed one has none): computed
    once per text, so that unclosed brackets do not each scan to its end.

    A quoted string holds its brackets, as in HTML and CSS: in a {...}, a
    value quoted after its `=` and closed before the end of its paragraph
    ({title="a } b"}); in a [...], a CSS string after `:`, `(` or `,` and
    closed on its line ([content:"]"]); the bracket opened in the same
    paragraph (one left open in the prose before holds none). An
    apostrophe elsewhere is text (l'eau)."""
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
                # a bracket left open in a paragraph before (prose: [0, 1)) holds no string
                end = quotes.closing(ch, i, across_lines=inner == '{') \
                    if quotes.same_paragraph(stacks[inner][-1], i) else None
                if end is not None:
                    i = end + 1
                    continue
        if ch in PAIRS:
            stacks[ch].append(i)
        elif ch in closing and stacks[closing[ch]]:
            matches[stacks[closing[ch]].pop()] = i
        i += 1
    return matches


# the group of each kind of bracket, as a field of TagElement
GROUP_FIELDS = {'()': 'parentheses', '[]': 'brackets', '{}': 'braces'}


@dataclass(slots=True, eq=False)
class TagElement:
    """A `name::` element as the source writes it: `tag` (the name, '' for a
    bare ::), from `start` (where the name starts) to `end`; its groups as
    written, `parentheses` (classes and id), `brackets` (style, or the
    label of a link), `braces` (HTML attributes), each group written twice
    joined with a space; `text`, the word after `::`; `groups`, (kind,
    start, end) of each group, its content text[start:end]; `stray`: a
    closing bracket without its opening one, all of it is text.

    The parser of the tree adds where it is (`line`, `column`, `context`:
    what a message quotes), `inline` (written name::text::), `label` (the
    nodes of the label of a link) and `warned` (what follows from it is
    warned already)."""
    tag: str = ''
    start: int = 0
    end: int = 0
    parentheses: str = ''
    brackets: str = ''
    braces: str = ''
    text: str = ''
    groups: list = field(default_factory=list)
    stray: bool = False
    line: int | None = None
    column: int | None = None
    context: str = ''
    inline: bool = False
    label: list | None = None
    warned: bool = False

    def group(self, kind):
        return getattr(self, GROUP_FIELDS[kind])

    def set_group(self, kind, value):
        setattr(self, GROUP_FIELDS[kind], value)

    def add_group(self, kind, value):
        written = self.group(kind)
        self.set_group(kind, f'{written} {value}' if written else value)

    def clear_groups(self):
        self.parentheses = self.brackets = self.braces = ''


def extract_bracket_elements(text, index_start):
    """The element whose `::` ends at `index_start`, a TagElement.

    A closing bracket without its opening one makes the whole element text
    (its groups are still listed, so that their content stays literal).
    An unclosed bracket raises LHTMLParseError."""
    element = TagElement(start=index_start, end=index_start)
    if index_start >= 2:
        name_end = index_start - 2
        m = _TAG_NAME_BEFORE.search(text, max(0, name_end - _MAX_TAG_NAME), name_end)
        tag_start = m.start() if m else name_end
        element.tag = text[tag_start:name_end]
        element.start = tag_start

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
                raise LHTMLParseError(f'{ch!r} has no closing {close!r}')
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

    element.end = i
    element.groups = groups     # protected from formatting even in a stray element
    if stray:                   # not a tag element: all of it is text
        element.stray = bool(groups)
        element.text = text[index_start:i]
        return element
    element.text = ''.join(word)
    for kind, start, end in groups:
        element.add_group(kind, text[start:end])
    return element


# ---------------------------------------------------------------------------
# Whether a :: is a tag
# ---------------------------------------------------------------------------

def is_closing_tag(element):
    """A bare :: (empty tag, span of exactly 2) is a closing tag."""
    return element.tag == '' and element.end - element.start == 2


def refuse_explicit_closing(element):
    """::[-] and ::name[-] were removed in LHTML 3.0: a tag is closed by ::.
    On a named tag, x::[-] is a style '-' (as in LHTML 2): kept, with a
    warning, since it was most likely meant as a closing tag."""
    context = element.context
    if element.tag == '':
        raise LHTMLParseError(f'::[-] was removed in LHTML 3.0; close a tag with :: (near {context!r})',
                              element.line, element.column)
    element.warned = True            # what follows from it is not warned again
    if element.tag == 'code':
        warn(f'code::[-] closes no code block; a block opens with code::[language] '
              f'(near {context!r})', element, stacklevel=5)
        return
    warn(f"{element.tag}::[-]: [-] is a style here, not a closing tag; close a tag with :: "
          f'(near {context!r})', element, stacklevel=5)


def is_tag_boundary(text, index, tag, last_tag_end=-1):
    """True if a tag (named, or bare :: when tag is '') may start at `index`.

    A tag name must not be glued to a preceding word (x.link::, std::a::).
    A bare :: must not follow an opening bracket or a word character, which
    leaves constructs like a[::2] or 2::3 untouched. A tag may always
    directly follow the previous tag.
    """
    if index == 0 or index == last_tag_end:
        return True
    ch = text[index - 1]
    if ch.isalnum() or ch in '_:':
        return False
    if tag:
        return ch not in '-.'
    return ch not in '[({'


def adjust_bare_tag(text, m, element):
    """Adjust the extent of a bare :: tag. Returns False if it is not a tag.

    - '::nl' followed by other characters is a spacer ending after 'nl'.
    - '::' followed by punctuation (e.g. '::,' or '::**') is a closing tag.
    - A '::' between two protected zones (e.g. <span>::</span> in
      pre-highlighted C++), or glued after one and followed by a word,
      is not a tag.
    """
    after_placeholder = m.start() > 0 and text[m.start() - 1] == PLACEHOLDER_CHAR
    if after_placeholder and text[m.end():m.end() + 1] == PLACEHOLDER_CHAR:
        return False

    word = element.text
    if SPACER.match(word):
        if element.end != m.end() + 2:
            element.text, element.end = 'nl', m.end() + 2
            element.clear_groups()
        return True
    if after_placeholder and word[:1].isalnum():
        return False
    following = text[m.end():m.end() + 1]
    if following and not (following.isalnum() or following.isspace() or following in '[({'):
        element.text, element.end = '', m.end()
        element.clear_groups()
    return True
