"""Reading a source as LHTML reads it, for the tools around it (a site
generator's lint, its source map, a plugin): where the zones LHTML leaves as
they are lie, and what a tag writes.

    for zone in lhtml.zones(text):          # Zone(start, end, kind, tag, value)
        ...
    written = lhtml.read_tag(text, start)   # the Written of the tag at `start`

These are the patterns LHTML parses with: a tool that uses them agrees with
LHTML on what is code and what is text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .nodes import Written
from .patterns import URL_TAGS, URL_TOKEN, make_placeholder, protected_blocks, protected_zones
from .tag_parser import extract_bracket_elements

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


def zones(text: str, *, url_tags=URL_TAGS, code: re.Pattern | None = None, start: int = 0) -> list[Zone]:
    """The zones of `text` LHTML leaves as they are, in order, from `start`:
    one left-to-right pass, an outer zone owns what it holds (`<script>`
    in inline code is code). `url_tags`: the tags whose text is a URL, kept
    as written (the built-in ones; a macro with `url:` is one too: give
    them all); `code`: the pattern of the code blocks of another markup (the
    fenced ``` blocks of Markdown), in place of LHTML's code::[...]."""
    if code is None:
        pattern = protected_blocks(tuple(url_tags))
    else:
        pattern = re.compile(f'(?P<code>{code.pattern})|' + protected_zones(tuple(sorted(url_tags))),
                             re.DOTALL | code.flags)
    found = []
    for m in pattern.finditer(text, start):
        group = next(g for g in _KINDS if m.group(g) is not None)
        kind = _KINDS[group]
        if kind == 'jinja' and m.group(0).startswith('{#'):
            kind = 'comment'            # a Jinja comment writes nothing, as an HTML one
        if kind == 'url':
            found.append(Zone(m.start(), m.end(), kind, m.group('urltag')[:-2], m.group('url')))
        else:
            found.append(Zone(m.start(), m.end(), kind))
    return found


_NAME = re.compile(r'[A-Za-z][\w-]*::|::')
_URL = re.compile(URL_TOKEN)


def read_tag(text: str, start: int, *, url_tags=URL_TAGS) -> Written | None:
    """What the `name::` tag whose name starts at `start` writes: its
    Written (tag, text, groups as written...), as a Tag is given it; None
    when there is no `::` after a name there. The URL of a tag of
    `url_tags` is read whole (img::{{ base }}/a.png). A bracket without its
    closing one raises LHTMLParseError."""
    m = _NAME.match(text, start)
    if m is None:
        return None
    name, after = m.group(0)[:-2], m.end()
    url = None
    if name in url_tags:                # its URL, then its groups
        found = _URL.match(text, after)
        if found:
            url = found.group(0)
            text = text[:after] + make_placeholder('U', 0) + text[found.end():]
    element = extract_bracket_elements(text, after)
    word = element.text.replace(make_placeholder('U', 0), url) if url is not None else element.text
    inline = word.endswith('::')
    return Written(tag=name, text=word[:-2] if inline else word, inline=inline,
                   parentheses=element.parentheses, brackets=element.brackets, braces=element.braces)
