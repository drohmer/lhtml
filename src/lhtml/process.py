"""Core LHTML processing functions.

Each function transforms LHTML markup into HTML for one language
feature (headings, bold, lists, tags, etc.). The pipeline execution
order is managed by pipeline.py.

Content that must not be transformed is replaced early by placeholders
(see patterns.PLACEHOLDER) and restored at the end. The kinds of stored
content are listed in ProtectionStores.
"""

import os
import re
import warnings
from dataclasses import dataclass, field

import yaml

from .element_extract import extract_bracket_elements
from .export_html import (
    export_html_element_class_and_id, export_html_generic,
    check_is_closing_tag, check_is_explicit_closing_tag,
)
from .listing import process_listing  # noqa: F401 — re-exported
from .code import export_html_code
from .errors import (
    LHTMLFileNotFound, LHTMLTagStackError, LHTMLIncludeLoopError,
    LHTMLParseError, LHTMLWarning,
)
from .patterns import (
    YAML_FRONTMATTER, VERBATIM_BLOCK, CODE_BLOCK, PROTECTED, PROTECTED_BLOCKS,
    HEADING, BOLD, ITALIC, INLINE_CODE,
    COMMENT, INCLUDE, TAG_MARKER, SPACER,
    BLOCK_TAGS, LEADING_TAG, TRAILING_TAG, LEADING_PLACEHOLDER, TRAILING_PLACEHOLDER,
    JINJA_LINE, BLOCK_RAW, PREFORMATTED_TAG,
    MAX_INCLUDE_ITERATIONS, PLACEHOLDER_CHAR, PLACEHOLDER,
    regex_transform, store_to_index, restore_from_index, make_placeholder,
)


@dataclass
class ProtectionStores:
    """Content replaced by placeholders during processing.

    V: verbatim blocks (raw text)        C: code blocks (header, body)
    R: raw zones: HTML tags, comments, <script>/<style>, math
    I: inline code (content with < and > escaped)
    U: URL of link::/img::/video::/videoplay:: tags
    A: LHTML styles, classes/IDs and HTML attributes
    """
    V: list = field(default_factory=list)
    C: list = field(default_factory=list)
    R: list = field(default_factory=list)
    I: list = field(default_factory=list)
    U: list = field(default_factory=list)
    A: list = field(default_factory=list)  # LHTML attribute group contents

    def add(self, kind, entry):
        store = getattr(self, kind)
        store.append(entry)
        return make_placeholder(kind, len(store) - 1)

    def restore(self, text, kind, render_fn=None):
        return restore_from_index(text, kind, getattr(self, kind), render_fn)


# ---------------------------------------------------------------------------
# Input normalization
# ---------------------------------------------------------------------------

def normalize_input(text):
    """Normalize a source text: no BOM, LF line endings, no NUL character
    (which would be mistaken for a placeholder delimiter)."""
    if text.startswith('\ufeff'):
        text = text[1:]
    return text.replace('\r\n', '\n').replace(PLACEHOLDER_CHAR, '\ufffd')


def read_source(filename):
    """Read an LHTML source file (UTF-8, with or without BOM), normalized."""
    with open(filename, 'r', encoding='utf-8-sig') as fid:
        return normalize_input(fid.read())


# ---------------------------------------------------------------------------
# YAML front matter
# ---------------------------------------------------------------------------

def process_yaml(text):
    """Extract YAML front matter and return (remaining_text, meta_dict).

    The front matter must start the document. If its content is not a
    YAML mapping, the text is left untouched.
    """
    match = YAML_FRONTMATTER.search(text)
    if not match:
        return text, {}
    try:
        yaml_content = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        warnings.warn(f'Invalid YAML front matter ignored: {e}', LHTMLWarning, stacklevel=2)
        return text, {}
    if yaml_content is None:
        yaml_content = {}
    if not isinstance(yaml_content, dict):
        return text, {}
    return text[match.end():], yaml_content


# ---------------------------------------------------------------------------
# Verbatim and code blocks (protect / restore)
# ---------------------------------------------------------------------------

def process_verbatim_to_index(text, verbatim_index_store):
    """Replace verbatim blocks with placeholders."""
    return store_to_index(text, VERBATIM_BLOCK, 'V', verbatim_index_store,
                          lambda m: m.group('vbody'))


def process_verbatim_back_from_index(text, verbatim_index_store):
    """Restore verbatim blocks from placeholders."""
    return restore_from_index(text, 'V', verbatim_index_store)


def _code_language(header):
    m = re.search(r'\[([^\[\]\n]*)\]', header)
    return m.group(1) if m else ''


def render_code_block(entry, verbatim_store=None):
    """Highlight a stored (header, body) code block."""
    header, body = entry
    if verbatim_store is not None:
        body = restore_from_index(body, 'V', verbatim_store)
    return export_html_code(body, _code_language(header))


# ---------------------------------------------------------------------------
# Protected zones (raw HTML, inline code, URLs, math)
# ---------------------------------------------------------------------------

def escape_inline_code(content):
    """Escape < and > in inline code (& is kept so that entities written
    by hand, such as &lt;, still work)."""
    return content.replace('<', '&lt;').replace('>', '&gt;')


def render_inline_code(content):
    return f'<code class="code-inline">{content}</code>'


def process_protect(text, stores, directories=None, _stack=()):
    """Replace zones that LHTML must not transform with placeholders.

    Protected (the leftmost zone wins): HTML comments, <script>/<style>
    blocks, inline code, URLs of link::/img::/video:: tags, math
    ($...$, $$...$$, \\(...\\), \\[...\\]) and HTML tags themselves (so
    attribute values are never modified). Text between HTML tags is
    still processed. Jinja expressions, statements and comments are opaque.
    With directories supplied, code/verbatim blocks participate in the same
    left-to-right scan and code includes use those directories.
    """
    def _protect(m):
        if directories is not None:
            if m.group('verbatim') is not None:
                return stores.add('V', m.group('vbody'))
            if m.group('code') is not None:
                body = _expand_includes_raw(m.group('body'), directories, _stack)
                return stores.add('C', (m.group('header'), body))
        if m.group('icode') is not None:
            return stores.add('I', escape_inline_code(m.group('icode')))
        if m.group('url') is not None:
            return m.group('urltag') + stores.add('U', m.group('url'))
        return stores.add('R', m.group(0))
    pattern = PROTECTED if directories is None else PROTECTED_BLOCKS
    return regex_transform(text, pattern, _protect)


def process_protect_attributes(text, stores):
    """Hide attribute groups from formatting, keeping link labels active."""
    def _heading(m):
        if not m.group(2):
            return m.group(0)
        return f'{m.group(1)}({stores.add("A", m.group(2))}) {m.group(3)}'
    text = regex_transform(text, HEADING, _heading)

    parts, prev = [], 0
    for m in TAG_MARKER.finditer(text):
        if m.start() < prev:
            continue
        try:
            element = extract_bracket_elements(text, m.end())
        except LHTMLParseError:
            continue
        tag = element['tag']
        if tag in ('include', 'code', 'verbatim') or not _is_tag_boundary(
                text, m.start() - len(tag), tag):
            continue
        end = element['index_end']
        pos = m.end()
        while pos < end:
            opening = text[pos]
            if opening not in '([{':
                pos += 1
                continue
            closing = {'(': ')', '[': ']', '{': '}'}[opening]
            start = pos
            depth = 1
            pos += 1
            while pos < end and depth:
                if text[pos] == opening:
                    depth += 1
                elif text[pos] == closing:
                    depth -= 1
                pos += 1
            if depth or (tag == 'link' and opening == '['):
                continue
            parts.append(text[prev:start + 1])
            parts.append(stores.add('A', text[start + 1:pos - 1]))
            prev = pos - 1
    parts.append(text[prev:])
    return ''.join(parts)


def process_unprotect(text, stores):
    """Restore the raw zones and URLs protected by process_protect."""
    text = stores.restore(text, 'A')
    text = stores.restore(text, 'R')
    return stores.restore(text, 'U')


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def process_remove_comment(text):
    """Remove ::# comments (to the end of the line)."""
    return regex_transform(text, COMMENT, lambda m: '')


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
    """Expand include:: directives (one level). Returns (new_text, found_any)."""
    found_include = False
    parts = []
    prev = 0

    for m in INCLUDE.finditer(text):
        if m.start() < prev:
            continue
        found_include = True
        element = extract_bracket_elements(text, m.end())
        filename = find_file(directory, element['text'])
        included = read_source(filename)

        parts.append(text[prev:m.start()])
        parts.append(included)
        prev = element['index_end']

    parts.append(text[prev:])
    return ''.join(parts), found_include


def _include_target(text, m, directories, stack):
    """Resolve the include:: directive matched by m. Returns (element, filename)."""
    element = extract_bracket_elements(text, m.end())
    filename = os.path.abspath(find_file(directories, element['text']))
    if filename in stack or len(stack) >= MAX_INCLUDE_ITERATIONS:
        raise LHTMLIncludeLoopError(MAX_INCLUDE_ITERATIONS, chain=[*stack, filename])
    return element, filename


def _expand_includes_raw(text, directories, _stack=()):
    """Expand include:: directives without any other processing (code blocks)."""
    parts = []
    prev = 0
    for m in INCLUDE.finditer(text):
        if m.start() < prev:
            continue
        element, filename = _include_target(text, m, directories, _stack)
        included = read_source(filename)
        included = _expand_includes_raw(included, [os.path.dirname(filename) + '/', *directories],
                                        (*_stack, filename))
        parts.append(text[prev:m.start()])
        parts.append(included)
        prev = element['index_end']
    parts.append(text[prev:])
    return ''.join(parts)


def process_include_recursive(text, directories, stores, _stack=()):
    """Prepare a file and expand its include:: directives recursively.

    In each file, verbatim/code blocks and protected zones are replaced
    by placeholders and comments are removed before includes are
    expanded, so that include:: or ::# inside code, HTML comments, etc.
    are left alone. An included file looks for its own includes first in
    its own directory, then in `directories`.
    Raises LHTMLIncludeLoopError on circular or too deep inclusion.
    """
    text = process_protect(text, stores, directories, _stack)
    text = process_protect_attributes(text, stores)
    text = process_remove_comment(text)

    parts = []
    prev = 0
    for m in INCLUDE.finditer(text):
        if m.start() < prev:
            continue
        element, filename = _include_target(text, m, directories, _stack)
        # The front matter of an included file is not part of its content
        included, _ = process_yaml(read_source(filename))
        file_directories = [os.path.dirname(filename) + '/', *directories]
        included = process_include_recursive(included, file_directories,
                                             stores, (*_stack, filename))

        parts.append(text[prev:m.start()])
        parts.append(included)
        prev = element['index_end']

    parts.append(text[prev:])
    return ''.join(parts)


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
    """Convert `text` to <code class="code-inline">text</code> (< and > escaped)."""
    return regex_transform(text, INLINE_CODE,
                           lambda m: render_inline_code(escape_inline_code(m.group(1))))


# ---------------------------------------------------------------------------
# Headings
# ---------------------------------------------------------------------------

def process_title(text, stores=None):
    """Convert = Title or =(.class) Title to <h1>Title</h1>, etc.

    With stores, the (.class #id) group protected by process_protect_attributes
    is resolved, and the generated attributes stay protected from inline
    formatting until process_unprotect.
    """
    def _heading(m):
        level = str(len(m.group(1)))
        class_id = m.group(2) or ''
        if stores is not None:
            class_id = stores.restore(class_id, 'A')
        class_id = class_id.strip()
        title = m.group(3)
        if class_id:
            attrs = export_html_element_class_and_id(class_id)
            if stores is not None and attrs:
                attrs = stores.add('A', attrs)
            return f'<h{level}{attrs}>{title}</h{level}>\n'
        return f'<h{level}>{title}</h{level}>\n'
    return regex_transform(text, HEADING, _heading)


# ---------------------------------------------------------------------------
# Code blocks
# ---------------------------------------------------------------------------

def process_code(text):
    """Highlight the raw code:: blocks contained in text."""
    return regex_transform(text, CODE_BLOCK,
                           lambda m: render_code_block((m.group('header'), m.group('body'))))


# ---------------------------------------------------------------------------
# Tag elements (the :: system)
# ---------------------------------------------------------------------------

def _warn_unmatched_closing(element):
    """Warn about a closing :: without opening tag; the source is kept."""
    warnings.warn(str(LHTMLTagStackError(element.get('context', ''))),
                  LHTMLWarning, stacklevel=4)
    return '', False


def _dispatch_tag(element, tag_to_close, current_directory, registry=None):
    """Dispatch a parsed tag element to the appropriate handler.

    Named tags go to the plugin registry if provided, then to the global
    registry (built-in tags). Unnamed tags (::) are closing tags, spacers
    or anonymous divs.
    """
    tag = element['tag']

    if tag != '':
        from .pipeline import tag_registry
        handler = (registry.get(tag) if registry is not None else None) or tag_registry.get(tag)
        if handler is not None:
            return handler(element, tag_to_close, current_directory)
        # Unrecognized tag — pass through
        return '', False

    # Explicit closing tag: ::div[-], ::span[-], or ::[-]
    if check_is_explicit_closing_tag(element) or (
            element['[]'] == '-' and not (element['text'] or element['()'] or element['{}'])):
        closing_name = element['text']
        if not tag_to_close:
            return _warn_unmatched_closing(element)
        if closing_name and closing_name not in (tag_to_close[-1],
                                                 getattr(tag_to_close[-1], 'name', None)):
            warnings.warn(
                f'Closing ::{closing_name}[-] but last opened tag is <{tag_to_close[-1]}> '
                f'(near {element.get("context", "")!r})',
                LHTMLWarning, stacklevel=3,
            )
        return '</' + tag_to_close.pop() + '>', True

    if check_is_closing_tag(element):
        if not tag_to_close:
            return _warn_unmatched_closing(element)
        return '</' + tag_to_close.pop() + '>', True
    if element['text'] == 'nl':
        return '<div style="height:1em;"></div>', True
    if element['[]'] or element['()'] or element['{}'] or element['text']:
        return export_html_generic(element, 'div', tag_to_close), True
    return '', False


def _context(text, start, end, max_len=40):
    """Short excerpt of the source around a tag, for warning messages."""
    excerpt = PLACEHOLDER.sub('…', text[start:min(end, start + max_len)])
    return excerpt.split('\n')[0]


def _is_tag_boundary(text, index, tag, last_tag_end=-1):
    """True if a tag (named, or bare :: when tag is '') may start at `index`.

    A tag name must not be glued to a preceding word (x.link::, std::a::).
    A bare :: must not follow an opening bracket, a colon or a word
    character, which leaves constructs like a[::2] or 2::3 untouched
    (except ':::' as in 'x:::nl', read as ':' followed by '::nl').
    A tag may always directly follow the previous tag.
    """
    if index == 0 or index == last_tag_end:
        return True
    ch = text[index - 1]
    if not tag and ch == ':':
        return index < 2 or not (text[index - 2].isalnum() or text[index - 2] in '_:')
    if ch.isalnum() or ch in '_:':
        return False
    if tag:
        return ch not in '-.'
    return ch not in '[({'


def _adjust_bare_tag(text, m, element):
    """Adjust the extent of a bare :: tag. Returns False if it is not a tag.

    - '::nl' followed by other characters is a spacer ending after 'nl'.
    - '::' followed by punctuation (e.g. '::,', '::**' or '::::[...]')
      is a closing tag.
    - A '::' between two protected zones (e.g. <span>::</span> in
      pre-highlighted C++), or glued after one and followed by a word,
      is not a tag.
    """
    after_placeholder = m.start() > 0 and text[m.start() - 1] == PLACEHOLDER_CHAR
    if after_placeholder and text[m.end():m.end() + 1] == PLACEHOLDER_CHAR:
        return False

    word = element['text']
    if SPACER.match(word):
        if element['index_end'] != m.end() + 2:
            element.update({'text': 'nl', '[]': '', '()': '', '{}': '',
                            'index_end': m.end() + 2})
        return True
    if after_placeholder and word[:1].isalnum():
        return False
    following = text[m.end():m.end() + 1]
    if following and not (following.isalnum() or following.isspace() or following in '[({'):
        element.update({'text': '', '[]': '', '()': '', '{}': '', 'index_end': m.end()})
    return True


def process_tag(text, current_directory='', registry=None, inline=False, resolve=None):
    """Process all :: tag elements in text.

    Args:
        inline: process only named tags (used inside inline code, where a
            bare :: is C++ syntax rather than LHTML).
        resolve: function applied to the parsed fields before dispatch
            (used to restore protected URLs).
    """
    parts = []
    prev = 0
    last_tag_end = -1
    tag_to_close = []
    open_contexts = []

    for m in TAG_MARKER.finditer(text):
        if m.start() < prev:
            continue  # skip overlapping matches

        try:
            element = extract_bracket_elements(text, m.end())
        except LHTMLParseError as e:
            warnings.warn(f'{e} near {_context(text, m.start(), m.end() + 30)!r}',
                          LHTMLWarning, stacklevel=2)
            continue
        tag = element['tag']
        tag_start = m.start() - len(tag)
        if tag_start < prev:
            # The name found backwards belongs to the previous tag (::nl::[...])
            tag, tag_start = '', m.start()
            element.update({'tag': '', 'index_start': tag_start})
        if not _is_tag_boundary(text, tag_start, tag, last_tag_end):
            continue
        if not tag and (inline or not _adjust_bare_tag(text, m, element)):
            continue
        context = text[tag_start:element['index_end']]
        if resolve is not None:
            context = resolve(context)
        element['context'] = _context(context, 0, len(context))
        if resolve is not None:
            for key in ('text', '[]', '()', '{}'):
                element[key] = resolve(element[key])

        depth = len(tag_to_close)
        html_out, is_real_tag = _dispatch_tag(element, tag_to_close, current_directory, registry)
        del open_contexts[len(tag_to_close):]
        open_contexts.extend([element['context']] * (len(tag_to_close) - depth))

        if is_real_tag:
            parts.append(text[prev:tag_start])
            parts.append(html_out)
            last_tag_end = element['index_end']
        else:
            parts.append(text[prev:element['index_end']])
        prev = element['index_end']

    for tag, context in zip(tag_to_close, open_contexts):
        warnings.warn(str(LHTMLTagStackError(context, unclosed=tag)), LHTMLWarning, stacklevel=2)

    parts.append(text[prev:])
    return ''.join(parts)


# ---------------------------------------------------------------------------
# Line breaks option
# ---------------------------------------------------------------------------

def _is_block_placeholder(kind, idx, stores):
    """True if a protected zone is a block: code/verbatim block, HTML
    comment, <script>/<style>, display math or block-level HTML tag."""
    if kind in 'CV':
        return True
    if kind != 'R':
        return False
    entry = stores.R[idx]
    if BLOCK_RAW.match(entry) or JINJA_LINE.fullmatch(entry):
        return True
    m = LEADING_TAG.match(entry)
    return bool(m) and m.group(1).lower() in BLOCK_TAGS


def _is_structure_line(line, stores):
    """True if the line starts or ends with a block element, or is a Jinja statement."""
    if JINJA_LINE.fullmatch(line):
        return True
    for tag_re, ph_re in ((LEADING_TAG, LEADING_PLACEHOLDER), (TRAILING_TAG, TRAILING_PLACEHOLDER)):
        m = ph_re.search(line)
        if m and _is_block_placeholder(m.group(1), int(m.group(2)), stores):
            return True
        m = tag_re.search(line)
        if m and m.group(1).lower() in BLOCK_TAGS:
            return True
    return False


def _preformatted_depth_change(line, stores):
    """Count actual preformatted tags, never tag-like text inside raw zones."""
    tags = []
    for placeholder in PLACEHOLDER.finditer(line):
        if placeholder.group(1) == 'R':
            entry = stores.R[int(placeholder.group(2))]
            # An actual tag starts at the beginning of its stored zone.
            # Do not scan inside comments, scripts, attributes or Jinja.
            tags.append(PREFORMATTED_TAG.match(entry))
    # Tags generated by handlers (and direct calls without stores) are
    # not placeholders. Tokenize them so quoted attributes stay opaque.
    for zone in PROTECTED.finditer(line):
        if zone.group('tag') is not None:
            tags.append(PREFORMATTED_TAG.match(zone.group('tag')))
    return sum(-1 if tag.group(1) else 1 for tag in tags if tag is not None)


def process_line_breaks(text, stores=None):
    """Make the line breaks of the source visible with <br>.

    Lines that start or end with a block element (heading, list, div,
    code block, ...) are structure and are left alone. In each run of
    other lines, blank lines at the start and end of the run are ignored,
    and every line but the last one gets a <br>, blank lines included.
    The content of protected zones (code, math, scripts...) is not
    affected since it is still hidden in placeholders, nor is the content
    of <pre> and <textarea> elements, whose line breaks are already visible.
    """
    if stores is None:
        stores = ProtectionStores()
    lines = text.split('\n')
    structure = []
    depth = 0
    for line in lines:
        change = _preformatted_depth_change(line, stores)
        structure.append(depth > 0 or change != 0 or _is_structure_line(line, stores))
        depth = max(0, depth + change)
    blank = [not line.strip() for line in lines]

    start = 0
    while start < len(lines):
        if structure[start]:
            start += 1
            continue
        end = start
        while end < len(lines) and not structure[end]:
            end += 1
        # run = lines[start:end], without leading/trailing blank lines
        first, last = start, end - 1
        while first <= last and blank[first]:
            first += 1
        while last >= first and blank[last]:
            last -= 1
        for k in range(first, last):
            lines[k] += '<br>'
        start = end
    return '\n'.join(lines)
