"""Core LHTML processing functions.

Each function transforms LHTML markup into HTML for one language
feature (headings, bold, lists, tags, etc.). The pipeline execution
order is managed by pipeline.py.
"""

import os
import re
import warnings

import yaml

from .element_extract import extract_bracket_elements
from .export_html import (
    export_html_element_class_and_id, export_html_generic,
    export_html_link, export_html_img, export_html_video,
    check_is_closing_tag, check_is_explicit_closing_tag,
)
from .listing import process_listing  # noqa: F401 — re-exported
from .code import export_html_code
from .errors import LHTMLFileNotFound, LHTMLTagStackError
from .patterns import (
    YAML_FRONTMATTER, VERBATIM_BLOCK, VERBATIM_INDEX,
    CODE_BLOCK, HEADING, BOLD, ITALIC, INLINE_CODE,
    COMMENT, INCLUDE, TAG_MARKER,
    VERBATIM_OPEN, VERBATIM_CLOSE, CODE_CLOSE, SPACER_TAG,
    regex_transform,
)


# ---------------------------------------------------------------------------
# YAML front matter
# ---------------------------------------------------------------------------

def process_yaml(text):
    """Extract YAML front matter and return (remaining_text, meta_dict)."""
    match = YAML_FRONTMATTER.search(text)
    if match:
        new_text = text[:match.start()] + text[match.end():]
        try:
            yaml_content = yaml.load(match.group(1), Loader=yaml.FullLoader) or {}
        except yaml.YAMLError:
            yaml_content = {}
        return new_text, yaml_content
    return text, {}


# ---------------------------------------------------------------------------
# Verbatim blocks (protect / restore)
# ---------------------------------------------------------------------------

def process_verbatim_to_index(text, verbatim_index_store):
    """Replace verbatim blocks with indexed placeholders."""
    def _store(m):
        content = m.group(0)[len(VERBATIM_OPEN):-len(VERBATIM_CLOSE)]
        idx = len(verbatim_index_store)
        verbatim_index_store.append(content)
        return f'verbatim::[{idx}]'
    return regex_transform(text, VERBATIM_BLOCK, _store)


def process_verbatim_back_from_index(text, verbatim_index_store):
    """Restore verbatim blocks from indexed placeholders."""
    def _restore(m):
        return verbatim_index_store[int(m.group(1))]
    return regex_transform(text, VERBATIM_INDEX, _restore)


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def process_remove_comment(text):
    """Remove ::#comment lines."""
    return regex_transform(text, COMMENT, lambda m: '\n')


# ---------------------------------------------------------------------------
# File inclusion
# ---------------------------------------------------------------------------

def find_file(directories, filename):
    """Locate a file in the given directory list."""
    for d in directories:
        pathname = os.path.join(d, filename)
        if os.path.isfile(pathname):
            return pathname
    raise LHTMLFileNotFound(filename, directories)


def process_include(text, directory):
    """Expand include:: directives. Returns (new_text, found_any)."""
    found_include = False
    parts = []
    prev = 0

    for m in INCLUDE.finditer(text):
        found_include = True
        element = extract_bracket_elements(text, m.end())
        filename = find_file(directory, element['text'])

        with open(filename, 'r') as fid:
            included = fid.read()

        parts.append(text[prev:m.start()])
        parts.append(included)
        prev = element['index_end']

    parts.append(text[prev:])
    return ''.join(parts), found_include


# ---------------------------------------------------------------------------
# Inline formatting
# ---------------------------------------------------------------------------

def process_bold(text):
    """Convert **text** to <strong>text</strong>."""
    return regex_transform(text, BOLD, lambda m: f'<strong>{m.group(1)}</strong>')


def process_italic(text):
    """Convert __text__ to <em>text</em>."""
    return regex_transform(text, ITALIC, lambda m: f'<em>{m.group(1)}</em>')


def process_code_inline(text):
    """Convert `text` to <code class="code-inline">text</code>."""
    return regex_transform(text, INLINE_CODE,
                           lambda m: f'<code class="code-inline">{m.group(1)}</code>')


# ---------------------------------------------------------------------------
# Headings
# ---------------------------------------------------------------------------

def process_title(text):
    """Convert = Title or =(.class) Title to <h1>Title</h1>, etc."""
    def _heading(m):
        level = str(len(m.group(1)))
        class_id = (m.group(2) or '').strip()
        title = m.group(3)
        if class_id:
            attrs = export_html_element_class_and_id(class_id)
            return f'<h{level}{attrs}>{title}</h{level}>\n'
        return f'<h{level}>{title}</h{level}>\n'
    return regex_transform(text, HEADING, _heading)


# ---------------------------------------------------------------------------
# Code blocks
# ---------------------------------------------------------------------------

def process_code(text):
    """Parse and highlight code:: blocks."""
    def _highlight(m):
        element = extract_bracket_elements(text, m.start() + len('code::'))
        code = text[element['index_end']:m.end() - len(CODE_CLOSE)]
        language = element['[]']
        return export_html_code(code, language)
    return regex_transform(text, CODE_BLOCK, _highlight)


# ---------------------------------------------------------------------------
# Tag elements (the :: system)
# ---------------------------------------------------------------------------

def _dispatch_tag(element, tag_to_close, current_directory, registry=None):
    """Dispatch a parsed tag element to the appropriate handler.

    Uses the tag_registry if provided, otherwise falls back to
    built-in dispatch for backward compatibility.
    """
    tag = element['tag']

    # Explicit closing tag: ::div[-], ::span[-], etc.
    if check_is_explicit_closing_tag(element):
        closing_name = element['text']
        if not tag_to_close:
            warnings.warn(
                str(LHTMLTagStackError(source_pos=element.get('index_start', -1))),
                stacklevel=3,
            )
            return '::??ERROR', True
        if tag_to_close[-1] != closing_name:
            warnings.warn(
                f'Closing ::{closing_name}[-] but last opened tag is <{tag_to_close[-1]}> '
                f'(position {element.get("index_start", -1)})',
                stacklevel=3,
            )
        return '</' + tag_to_close.pop() + '>', True

    # Try plugin registry first
    if registry is not None:
        handler = registry.get(tag)
        if handler is not None:
            return handler(element, tag_to_close, current_directory)

    # Built-in tag dispatch (used when no registry, or tag not in registry)
    if tag == 'div' or tag == 'span':
        return export_html_generic(element, tag, tag_to_close), True
    elif tag == 'link':
        return export_html_link(element), True
    elif tag == 'img':
        return export_html_img(element), True
    elif tag == 'video':
        return export_html_video(element, '', current_directory), True
    elif tag == 'videoplay':
        return export_html_video(element, 'autoplay loop muted', current_directory), True
    elif tag == '':
        if check_is_closing_tag(element):
            if not tag_to_close:
                warnings.warn(
                    str(LHTMLTagStackError(source_pos=element.get('index_start', -1))),
                    stacklevel=3,
                )
                return '::??ERROR', True
            return '</' + tag_to_close.pop() + '>', True
        if element['text'] == SPACER_TAG:
            return '<div style="height:1em;"></div>', True
        if element['[]'] or element['()'] or element['{}'] or element['text']:
            return export_html_generic(element, 'div', tag_to_close), True
        return '', False

    # Unrecognized tag — pass through
    return '', False


def process_tag(text, current_directory='', registry=None):
    """Process all :: tag elements in text."""
    parts = []
    prev = 0
    tag_to_close = []

    for m in TAG_MARKER.finditer(text):
        if m.start() <= prev:
            continue  # skip overlapping matches

        element = extract_bracket_elements(text, m.end())
        html, is_real_tag = _dispatch_tag(element, tag_to_close, current_directory, registry)
        tag = element['tag']
        index_end = element['index_end']

        if is_real_tag:
            parts.append(text[prev:m.start() - len(tag)])
            parts.append(html)
        else:
            parts.append(text[prev:index_end])
        prev = index_end

    parts.append(text[prev:])
    return ''.join(parts)
