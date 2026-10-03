"""HTML document wrapping for LHTML.

Wraps LHTML output in a complete HTML5 document structure
with head, meta, CSS/JS includes from the YAML metadata.
"""

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


def _ensure_list(value):
    """Normalize a string-or-list meta value to a list."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return value
    return []


def wrap_auto(html_in, meta):
    """Wrap content in a full HTML5 document using meta configuration."""
    head_parts = []

    for css in _ensure_list(meta.get('css', [])):
        head_parts.append(f'\t<link rel="stylesheet" type="text/css" href="{escape(str(css))}">\n')

    for js in _ensure_list(meta.get('js', [])):
        head_parts.append(f'\t<script src="{escape(str(js))}" defer></script>\n')

    return HTML_TEMPLATE.format(
        title=escape(str(meta.get('title', 'Webpage')), quote=False),
        head_extras=''.join(head_parts),
        content=html_in,
    )
