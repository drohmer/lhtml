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
from .nodes import Written
from .patterns import URL_TAGS, URL_TOKEN, protected_blocks, protected_zones, zones_in
from .process import MarksOnLine, url_and_closing_marks
from .tag_parser import extract_bracket_elements
from .tags import Tag
from .code import checked_lexers
from .tree import _parse, registry

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
    flags = 's' + ''.join(letter for letter, flag in (('a', re.A), ('i', re.I), ('m', re.M), ('x', re.X))
                          if code.flags & flag)    # its own, not those of the other zones
    end = '\n' if code.flags & re.X else ''        # (re.X: a # comment ends with its line)
    return re.compile(f'(?P<code>(?{flags}:{code.pattern}{end}))|' + protected_zones(tuple(sorted(url_tags))),
                      re.DOTALL)


def zones(text: str, *, url_tags: Iterable[str] = URL_TAGS, code: re.Pattern | None = None,
          start: int = 0) -> list[Zone]:
    """The zones of `text` LHTML leaves as they are, in order, from `start`:
    one left-to-right pass, an outer zone owns what it holds (`<script>`
    in inline code is code). `url_tags`: the tags whose text is a URL, kept
    as written (the built-in ones; a macro with `url:` is one too: give
    them all); `code`: the pattern of the code blocks of another markup (the
    fenced ``` blocks of Markdown), in place of LHTML's code::[...]."""
    found, marks = [], MarksOnLine(text)
    for m in zones_in(_pattern(url_tags, code), text, start):
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


def read_tags(text: str, names: Iterable[str] | None = None, *, tags: Mapping[str, Tag] | None = None,
              macros: Mapping | None = None) -> Iterator[SourceTag]:
    """The tags parse reads in `text`, in order, each with its own rules
    (parse notes them as it reads), so a tool agrees with LHTML: a tag in a
    code block, a comment, inline code or a URL is none, a URL ends where
    parse ends it (**img::a.png**), a tag in a link's label is one, a
    container there is text, a name that is no tag is text (std::vector).

    `tags` and `macros`: those of the run, as parse takes them (a tag of a
    tool: tags={'includeadv': lhtml.Tag(build)}). `names`: a filter, those
    tags only (it changes nothing of what is read). Each SourceTag(start,
    end, written): the tag at text[start:end] (a container: its opening,
    `div::(.c)`), `written` as its Tag got it (a link's label: its nodes).
    A syntax removed in 3.0, or an error of a tag, raises as in parse."""
    run = registry(tags, macros)
    wanted = set(run) if names is None else set(names)
    _, read = _parse(text, run, checked_lexers(None), False)
    for (start, end), written in sorted(read, key=lambda pair: pair[0]):
        if written.tag in wanted:
            yield SourceTag(start, end, written)


@functools.lru_cache(maxsize=8)
def _line_starts(text):
    """Where each line of a text starts: computed once per text."""
    return [0] + [m.end() for m in re.finditer('\n', text)]


_ONE_NAME = re.compile(r'(?<![\w-])[A-Za-z][\w-]*::')
_URL = re.compile(URL_TOKEN)


def read_tag(text: str, start: int, *, url_tags: Iterable[str] = URL_TAGS) -> SourceTag | None:
    """The tag written at `start`, any name, read as syntax: the text as it
    is, wherever it is (in a code block too), what a tool replaces before
    LHTML reads the page; read_tags gives what parse reads. None if no name
    and :: start there (pan:: in span:: is none). Its groups, and its URL
    whole for a tag of `url_tags`; no markup around it is read (a bold, a
    link's label: in **img::a.png** its URL is a.png**). `written` holds
    its tag, text, inline, groups as written, line, column and context, no
    label. A bracket without its closing one raises LHTMLParseError; a
    `start` outside the text, ValueError. Its brackets and lines are read
    once per text: a page read tag by tag stays linear, each call reading
    its own tag (tags glued in one word, a::a::a, each read to its end, are
    read in the time of their lengths)."""
    if not 0 <= start <= len(text):
        raise ValueError(f'start: {start} is not a place in the text (0 to {len(text)})')
    m = _ONE_NAME.match(text, start)
    if m is None:
        return None
    name, after = m.group(0)[:-2], m.end()
    lines = _line_starts(text)
    line = bisect.bisect_right(lines, start)
    url = None
    if name in frozenset(url_tags):     # its URL first: kept as written
        found = _URL.match(text, after)
        if found:
            url = found.group(0)
            after = found.end()
    element = extract_bracket_elements(text, name, start, after, after_text=url is not None)
    word = (url or '') + element.text
    inline = word.endswith('::')
    return SourceTag(start, element.end, Written(
        tag=name, text=word[:-2] if inline else word, inline=inline,
        parentheses=element.parentheses, brackets=element.brackets, braces=element.braces,
        line=line, column=start - lines[line - 1] + 1, context=quote(text, start, element.end)))
