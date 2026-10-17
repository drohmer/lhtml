"""The HTML of the tag elements, and the tags: Tag, the built-in TAGS.

Each export_html_* function converts a parsed element dict into an HTML
string. The element dict has keys: '[]' (style), '()' (class/id), '{}'
(inline attrs), 'text', 'tag' (see tag_parser.extract_bracket_elements).
"""

import html
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable

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

def _written(elements, name):
    """Whether the attributes {...} of an element write `name`: then they
    replace the one the tag would give (img::a.png{alt="A"}: one alt)."""
    return re.search(rf'(?<![\w-]){name}\s*=', elements['{}'] or '') is not None


def export_html_link(elements):
    """Render a link:: element as <a href="...">text</a>."""
    attrs = export_html_element_class_and_id(elements['()'])
    attrs += export_html_element_inline(elements['{}'])
    href = '' if _written(elements, 'href') else f' href="{_attr(elements["text"])}"'
    return f'<a{attrs}{href}>{elements["[]"]}</a>'


def export_html_img(elements):
    """Render an img:: element as <img src="..." alt="...">; an alt or a src
    written in its attributes replaces the default."""
    src = elements['text']
    defaults = ''.join(f' {name}="{_attr(src)}"' for name in ('src', 'alt') if not _written(elements, name))
    return f'<img{_build_attrs(elements)}{defaults}>'


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
# The tags
# ---------------------------------------------------------------------------

@dataclass
class Tag:
    """A `name::` tag. `container`: whether it holds what follows until its
    `::` (a bool, or a function of the element); written `name::text::`, it
    holds nothing either way. `render(element, children, context)`: its
    HTML, closing tag included; `children` is the HTML of what it holds (''
    for a tag that holds nothing), and element['closed'] is False when
    nothing closed it. `context` is the ProcessingContext of the run
    (context.meta, context.media)."""
    render: Callable
    container: bool | Callable = False
    url: bool = False               # its text is a URL, kept as written (img::a__b.png)

    def holds(self, element):
        if element['text'].endswith('::'):
            return False
        return self.container(element) if callable(self.container) else bool(self.container)


def element_html(tag, element, children):
    """<tag attributes>text, then what it holds and </tag> (or <tag>text</tag>
    for div::text::)."""
    text = element['text']
    if text.endswith('::'):
        return f'<{tag}{_build_attrs(element)}>{text[:-2]}</{tag}>'
    return (f'<{tag}{_build_attrs(element)}>{text}' + children
            + (f'</{tag}>' if element.get('closed', True) else ''))


def generic(tag):
    """div::, span::: holds what follows, unless written div::text::"""
    return Tag(lambda element, children, context: element_html(tag, element, children), container=True)


# Read-only: a run adds its own tags with run(..., tags=)
TAGS = MappingProxyType({
    'div': generic('div'),
    'span': generic('span'),
    'link': Tag(lambda element, children, context: export_html_link(element), url=True),
    'img': Tag(lambda element, children, context: export_html_img(element), url=True),
    'video': Tag(lambda element, children, context: export_html_video(element, '', context.media), url=True),
    'videoplay': Tag(lambda element, children, context: export_html_video(
        element, 'autoplay loop muted playsinline', context.media), url=True),
})

SPACER = Tag(lambda element, children, context: '<div style="height:1em;"></div>')     # ::nl
