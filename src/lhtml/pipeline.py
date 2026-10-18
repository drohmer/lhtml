"""The run of LHTML: the text parsed into a document tree, and rendered
(lhtml/tree.py).

Content that must not be transformed (code, raw HTML, math, inline code)
is a leaf of the tree, never read as LHTML; headings, lists, bold, italic
and the :: elements are its nodes.
"""

from __future__ import annotations

from collections.abc import Mapping

from .tags import Tag
from .render import Media, render
from .tree import parse


def run(text: str, *, macros: Mapping[str, Mapping | None] | None = None, tags: Mapping[str, Tag] | None = None,
        line_breaks: bool = False, media: Media | None = None,
        lexers: Mapping[str, type] | None = None) -> str:
    """Convert LHTML text to HTML (the content of a page: lhtml.wrap makes a
    document of it).

    macros: the definitions of the macros, a mapping (lhtml.load_macros
        reads them from YAML files).
    tags: custom tags {name: lhtml.Tag}, added to the built-in TAGS and the
        macros (a tag given wins).
    line_breaks: the line breaks of the source are rendered as <br>.
    media: media(src) -> [(url, mime type)], the sources of a video.
    lexers: {name: Pygments lexer class}, languages of the code blocks,
        before lhtml.LEXERS (a global: lexers= changes no other call).

    LHTML reads no file. The problems found are LHTMLWarning warnings and
    LHTMLError errors, with the `line` and `column` in `text` where they
    are (None if not known); to collect them without the warnings module,
    parse(text, warn=False) and render: document.problems.
    """
    return render(parse(text, macros=macros, tags=tags, lexers=lexers),
                  line_breaks=line_breaks, media=media, lexers=lexers)
