"""HTML generation functions for LHTML tag elements.

Each export_html_* function converts a parsed element dict into
an HTML string. The element dict has keys: '[]' (style), '()'
(class/id), '{}' (inline attrs), 'text', 'tag'.
"""

import html
import re

from .patterns import JINJA_RE


# ---------------------------------------------------------------------------
# Attribute helpers
# ---------------------------------------------------------------------------

def _build_attrs(elements):
    """Build the common HTML attribute string from an element dict."""
    parts = []
    parts.append(export_html_element_class_and_id(elements['()']))
    parts.append(export_html_element_style(elements['[]']))
    parts.append(export_html_element_inline(elements['{}']))
    return ''.join(parts)


def _attr(value):
    """Escape the double quotes of a value placed inside a double-quoted HTML
    attribute (Jinja zones are kept as is, they are rendered before HTML)."""
    parts, prev = [], 0
    for m in JINJA_RE.finditer(value):
        parts.append(value[prev:m.start()].replace('"', '&quot;'))
        parts.append(m.group(0))
        prev = m.end()
    parts.append(value[prev:].replace('"', '&quot;'))
    return ''.join(parts)


def export_html_element_style(text):
    if not text:
        return ''
    return f' style="{_attr(text)}"'


def export_html_element_class_and_id(text):
    """Parse '.class1 .class2 #id' (or '.class1.class2#id') into class="..."
    id="..." attributes."""
    if not text:
        return ''
    classes = []
    ids = []
    for token in text.split():
        if not token.startswith(('.', '#')):
            continue
        for part in re.findall(r'[.#][^.#]+', token):
            (classes if part[0] == '.' else ids).append(part[1:])
    parts = []
    if classes:
        parts.append(f' class="{" ".join(classes)}"')
    if ids:
        parts.append(f' id="{" ".join(ids)}"')
    return ''.join(parts)


def export_html_element_inline(text):
    if not text:
        return ''
    return ' ' + text


# ---------------------------------------------------------------------------
# Tag element renderers
# ---------------------------------------------------------------------------

def export_html_generic(elements, tag, tag_to_close):
    """Render a generic div/span element."""
    html = f'<{tag}{_build_attrs(elements)}>'

    text = elements['text']
    if text:
        if text.endswith('::'):
            text = text[:-2]
            html += text + f'</{tag}>'
            return html
        html += text

    tag_to_close.append(tag)
    return html


def export_html_link(elements):
    """Render a link:: element as <a href="...">text</a>."""
    attrs = export_html_element_class_and_id(elements['()'])
    attrs += export_html_element_inline(elements['{}'])
    return f'<a{attrs} href="{_attr(elements["text"])}">{elements["[]"]}</a>'


def export_html_img(elements):
    """Render an img:: element as <img src="..." alt="...">."""
    src = elements['text']
    return f'<img{_build_attrs(elements)} src="{_attr(src)}" alt="{_attr(src)}">'


# ---------------------------------------------------------------------------
# Video rendering
# ---------------------------------------------------------------------------

def export_html_video(elements, default_inline='', media=None):
    """Render a video:: or videoplay:: element.

    `media`, when given, is the caller's resolver: media(src) returns the
    sources to offer, as a list of (url, mime type), or an empty list for the
    source as written. LHTML probes no file for variants or posters."""
    source = elements['text']
    extension = source.rsplit('.', 1)[-1]
    mime_extension = re.split(r'[?#]', extension, maxsplit=1)[0].lower()

    parts = ['<video']
    parts.append(export_html_element_inline(elements['{}']))
    if default_inline:
        parts.append(f' {default_inline}')
    parts.append(export_html_element_class_and_id(elements['()']))
    parts.append(export_html_element_style(elements['[]']))
    parts.append('>\n')

    sources = list(media(source) or []) if media is not None else []
    if not sources:
        sources = [(source, f'video/{mime_extension}')]
    for url, mime in sources:
        parts.append(f'\t<source src="{_attr(url)}" type="{_attr(mime)}">\n')

    parts.append(f'\t Cannot play video {html.escape(source)}\n')
    parts.append('</video>')
    return ''.join(parts)


# ---------------------------------------------------------------------------
# Closing tag detection
# ---------------------------------------------------------------------------

def check_is_closing_tag(elements):
    """A bare :: (empty tag, span of exactly 2) is a closing tag."""
    return elements['tag'] == '' and elements['index_end'] - elements['index_start'] == 2

