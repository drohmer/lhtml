"""Reading a source as LHTML reads it, for the tools around it (a site
generator's lint, its source map, a plugin): where the zones LHTML leaves as
they are lie, and what a tag writes.

    for zone in lhtml.zones(text):              # Zone(start, end, kind, tag, value)
        ...
    for found in lhtml.read_tags(text, {'img'}):    # SourceTag(start, end, written)
        ...
    found = lhtml.read_tag(text, start)         # the tag written there, as syntax

zones reads with the patterns of parse, and its URL (one that ends before
the ** of a bold opened before it: **img::a.png**); read_tags is parse: a
tool agrees with LHTML on what is code, what is text and what a tag writes.
read_tag reads the syntax at a place, wherever it is (a plugin that
replaces a tag of its own before LHTML, in a code block too).
"""

from __future__ import annotations

import bisect
import functools
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import NamedTuple

from .errors import quote
from .nodes import Raw, Written
from .patterns import URL_TAGS, URL_TOKEN, protected_blocks, protected_zones
from .process import MarksOnLine, url_and_closing_marks
from .tag_parser import extract_bracket_elements
from .tags import Tag
from .tree import parse, registry

# The kinds of zones, as the groups of the patterns name them
_KINDS = {'code': 'code', 'jinja': 'jinja', 'comment': 'comment', 'raw': 'raw', 'icode': 'inline_code',
          'urltag': 'url', 'math': 'math', 'tag': 'tag'}


@dataclass(frozen=True)
class Zone:
    """A zone LHTML does not read as LHTML: text[start:end]. `kind`:

        code         a code block (code::[python] ... code::[-])
        jinja        a Jinja expression or statement ({{ x }}, {% if %})
        comment      an HTML or a Jinja comment (<!-- -->, {# #})
        raw          a <script> or a <style> and its content
        inline_code  `code`
        url          a tag and its URL, kept as written (img::a__b.png):
                     `tag` is the tag (img), `value` the URL
        math         \\(...\\) or \\[...\\]
        tag          an HTML tag (<div class="a">)
    """
    start: int
    end: int
    kind: str
    tag: str | None = None
    value: str | None = None


def _pattern(url_tags, code):
    if code is None:
        return protected_blocks(tuple(sorted(url_tags)))
    return re.compile(f'(?P<code>{code.pattern})|' + protected_zones(tuple(sorted(url_tags))),
                      re.DOTALL | code.flags)


def zones(text: str, *, url_tags: Iterable[str] = URL_TAGS, code: re.Pattern | None = None,
          start: int = 0) -> list[Zone]:
    """The zones of `text` LHTML leaves as they are, in order, from `start`:
    one left-to-right pass, an outer zone owns what it holds (`<script>`
    in inline code is code). `url_tags`: the tags whose text is a URL, kept
    as written (the built-in ones; a macro with `url:` is one too: give
    them all); `code`: the pattern of the code blocks of another markup (the
    fenced ``` blocks of Markdown), in place of LHTML's code::[...]."""
    found, marks = [], MarksOnLine(text)
    for m in _pattern(url_tags, code).finditer(text, start):
        group = next(g for g in _KINDS if m.group(g) is not None)
        kind = _KINDS[group]
        if kind == 'jinja' and m.group(0).startswith('{#'):
            kind = 'comment'            # a Jinja comment writes nothing, as an HTML one
        if kind == 'url':               # as parse reads it: **img::a.png** ends before its **
            url, after = m.group('url'), ''
            if url.endswith(('**', '__')):
                url, after = url_and_closing_marks(url, marks.before(m.start()))
            found.append(Zone(m.start(), m.end() - len(after), kind, m.group('urltag')[:-2], url))
        else:
            found.append(Zone(m.start(), m.end(), kind))
    return found


class SourceTag(NamedTuple):
    """A tag written in a source: text[start:end], and what it writes."""
    start: int
    end: int
    written: Written


_NAME = re.compile(r'([A-Za-z][\w-]*)::')
_SYNTAX = ('code', 'nl', 'include')    # LHTML syntax, not tags


def read_tags(text: str, names: Iterable[str] | None = None, *, macros: Mapping | None = None,
              url_tags: Iterable[str] = ()) -> Iterator[SourceTag]:
    """The tags written in `text`, in order, as parse reads them - parse
    reads them: each tag keeps what it is given - so a tool agrees with
    LHTML: a tag in a code block, a comment, inline code or a URL is none,
    a URL ends where parse ends it (**img::a.png**), a tag in a link's label
    is one, a name that is no tag is text (std::vector).

    `names`: those tags only, any name (includeadv: a tag of the tool); by
    default the tags of the run, the built-in ones and the `macros`.
    `url_tags`: names whose text is a URL besides those of the run (the
    built-in ones, the macros with `url:`). Each SourceTag(start, end,
    written): `written` as a Tag gets it (its label: the nodes of a link's
    label), the tag at text[start:end]. Every tag holds nothing here (an
    element that holds what follows is its opening, `div::(.c)`). A syntax
    removed in 3.0 raises LHTMLParseError, as parse does."""
    run = registry(None, macros)
    wanted = set(run) if names is None else set(names)
    wanted &= {m.group(1) for m in _NAME.finditer(text)}
    wanted -= set(_SYNTAX)
    url_tags = frozenset(url_tags) | {name for name, tag in run.items() if tag.url}
    found = []

    def keep(written):
        node = Raw('')
        found.append((node, written))
        return node
    tags = {name: Tag(keep, url=name in url_tags) for name in wanted}
    parse(text, macros=macros, tags=tags, warn=False)
    for node, written in sorted(found, key=lambda pair: pair[0].span):
        if node.line is not None and written.tag in wanted:
            yield SourceTag(node.span[0], node.span[1], written)


@functools.lru_cache(maxsize=8)
def _line_starts(text):
    """Where each line of a text starts: computed once per text."""
    return [0] + [m.end() for m in re.finditer('\n', text)]


_ONE_NAME = re.compile(r'[A-Za-z][\w-]*::')
_URL = re.compile(URL_TOKEN)


def read_tag(text: str, start: int, *, url_tags: Iterable[str] = URL_TAGS) -> SourceTag | None:
    """The tag written at `start` (its name, then ::, any name), read as
    syntax, wherever it is - in a code block too: what a tool replaces
    before LHTML reads the page (lhtml.read_tags gives what parse reads).
    SourceTag(start, end, written), None if no name and :: are there:
    `written` holds its tag, text, inline, groups as written, line, column
    and context, not a label (the nodes of a label are parse's). The text
    of a tag of `url_tags` is a URL as parse reads it: whole
    (img::{{ base }}/a.png), ending before the ** that closes a bold opened
    before it on its line (**img::a.png**). A bracket without its closing
    one raises LHTMLParseError. The text is read once for all the calls on
    it (its brackets matched once): read_tag reads a page tag by tag."""
    m = _ONE_NAME.match(text, start)
    if m is None:
        return None
    name, after = m.group(0)[:-2], m.end()
    lines = _line_starts(text)
    line = bisect.bisect_right(lines, start)
    marks = MarksOnLine(text, lines[line - 1], line)        # its line only: a page read tag by tag
    url, closing = None, ''
    if name in frozenset(url_tags):     # its URL first: kept as written
        found = _URL.match(text, after)
        if found:
            url = found.group(0)
            if url.endswith(('**', '__')):
                url, closing = url_and_closing_marks(url, marks.before(start))
            after = found.start() + len(url)
    if closing:                         # **img::a.png**: the bold ends it
        element, end = None, after
    else:                               # after a URL, a group ends the word, as in parse
        element = extract_bracket_elements(text, after, after_text=url is not None)
        end = element.end
    word = (url or '') + (element.text if element else '')
    inline = word.endswith('::')
    column = start - lines[line - 1] + 1
    return SourceTag(start, end, Written(
        tag=name, text=word[:-2] if inline else word, inline=inline,
        parentheses=element.parentheses if element else '', brackets=element.brackets if element else '',
        braces=element.braces if element else '', line=line, column=column, context=quote(text, start, end)))
