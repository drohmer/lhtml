"""HTML generation functions for LHTML tag elements.

Each export_html_* function converts a parsed element dict into
an HTML string. The element dict has keys: '[]' (style), '()'
(class/id), '{}' (inline attrs), 'text', 'tag'.
"""

import os


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


def export_html_element_style(text):
    if not text:
        return ''
    return f' style="{text}"'


def export_html_element_class_and_id(text):
    """Parse '.class1 .class2 #id' into class="..." id="..." attributes."""
    if not text:
        return ''
    classes = []
    ids = []
    for token in text.split():
        if token.startswith('.'):
            classes.append(token[1:])
        elif token.startswith('#'):
            ids.append(token[1:])
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
    return f'<a{attrs} href="{elements["text"]}">{elements["[]"]}</a>'


def export_html_img(elements):
    """Render an img:: element as <img src="..." alt="...">."""
    src = elements['text']
    return f'<img{_build_attrs(elements)} src="{src}" alt="{src}">'


# ---------------------------------------------------------------------------
# Video rendering with codec detection
# ---------------------------------------------------------------------------

CACHE_VIDEO_DIR = 'cache_video_codecs/'

VIDEO_CODECS = [
    ('-vp9.webm',  'video/webm'),
    ('-h265.mp4',  'video/mp4'),
    ('-h264.mp4',  'video/mp4'),
]


def export_html_video(elements, default_inline='', current_directory=''):
    """Render a video:: or videoplay:: element with codec variants."""
    source = elements['text']
    extension = source.rsplit('.', 1)[-1]
    poster_candidate = source.rsplit(f'.{extension}', 1)[0] + '-poster.jpg'

    parts = ['<video']
    parts.append(export_html_element_inline(elements['{}']))
    if default_inline:
        parts.append(f' {default_inline} ')
    parts.append(export_html_element_class_and_id(elements['()']))
    parts.append(export_html_element_style(elements['[]']))
    if os.path.isfile(poster_candidate):
        parts.append(f' poster="{poster_candidate}"')
    parts.append('>\n')

    # Look for transcoded codec variants
    source_name, _ = os.path.splitext(source)
    source_basename = os.path.basename(source_name)
    source_dirname = os.path.dirname(source_name)

    found_codecs = False
    if current_directory and os.path.basename(source_dirname) == 'assets':
        codec_dir = os.path.join(source_dirname, CACHE_VIDEO_DIR)
        full_codec_dir = os.path.join(current_directory, codec_dir)
        if os.path.isdir(full_codec_dir):
            for suffix, mime in VIDEO_CODECS:
                candidate = os.path.join(codec_dir, source_basename + suffix)
                if os.path.isfile(os.path.join(current_directory, candidate)):
                    parts.append(f'\t<source src="{candidate}" type="{mime}">\n')
                    found_codecs = True

    if not found_codecs:
        parts.append(f'\t<source src="{source}" type="video/{extension}">\n')

    parts.append(f'\t Cannot play video {source}\n')
    parts.append('</video>')
    return ''.join(parts)


# ---------------------------------------------------------------------------
# Closing tag detection
# ---------------------------------------------------------------------------

def check_is_closing_tag(elements):
    """A bare :: (empty tag, span of exactly 2) is a closing tag."""
    return elements['tag'] == '' and elements['index_end'] - elements['index_start'] == 2
