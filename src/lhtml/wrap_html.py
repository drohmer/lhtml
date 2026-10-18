"""HTML document wrapping for LHTML.

Wraps LHTML output in a complete HTML5 document structure
with head, meta, CSS/JS includes.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from html import escape

HTML_TEMPLATE = """\
<!DOCTYPE html>

<html lang="en">

<head>
\t<meta charset="utf-8">
\t<meta name="viewport" content="width=device-width, initial-scale=1">
\t<title>{title}</title>
{head_extras}\
</head>

<body>
{content}
</body>

</html>
"""


def _names(value, option):
    if isinstance(value, (str, os.PathLike)):
        return [value]
    if isinstance(value, Iterable):
        return list(value)
    raise TypeError(f'{option}: expected a file name or a list of them, got {type(value).__name__}')


def wrap(html_in: str, *, title: str = 'Webpage', css: str | Iterable[str] = (),
         js: str | Iterable[str] = ()) -> str:
    """A complete HTML5 document of the HTML of a page: its `title`, and the
    stylesheets `css` and scripts `js` it links (a name or a list)."""
    head_parts = []
    for name in _names(css, 'css'):
        head_parts.append(f'\t<link rel="stylesheet" type="text/css" href="{escape(str(name))}">\n')
    for name in _names(js, 'js'):
        head_parts.append(f'\t<script src="{escape(str(name))}" defer></script>\n')
    return HTML_TEMPLATE.format(
        title=escape(str(title), quote=False),
        head_extras=''.join(head_parts),
        content=html_in,
    )
