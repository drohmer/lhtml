"""Centralized regex patterns and text transformation utilities for LHTML."""

import re
from typing import Callable


# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

HEADING          = re.compile(r'^(=+)(?:\((.*?)\))? (.*?)$', re.MULTILINE)
BOLD             = re.compile(r'\*\*(.*?)\*\*')
ITALIC           = re.compile(r'__(.*?)__')
# include:: was removed in 3.0; still recognized, to be refused by name
INCLUDE          = re.compile(r'(?<![\w-])include::')
# Removed in 3.0 too, refused by name: ::# comments (a comment started a line
# or followed whitespace, so link::#anchor is not one) and verbatim:: blocks
REMOVED_COMMENT  = re.compile(r'(?<!\S)::#')
# (the empty group of verbatim::[] is a protected attribute by then)
REMOVED_VERBATIM = re.compile(r'(?<![\w`:-])verbatim::\[(?:\x00A(\d+)\x00)?\]')
# Exactly two colons: a run of three or more is text, not a tag
TAG_MARKER       = re.compile(r'(?<!:)::(?!:)')
# A node of the document tree, once a stage has read it: one character of
# the text the next stages read (lhtml/tree.py). It is a boundary, as the
# end of a line is: it ends the word of an element, and a tag may follow it.
EVENT_CHAR       = '\ue000'
SPACER           = re.compile(r'nl(?![\w-])')

# Block directives must not follow a backquote (inline code) or a colon.
# A code block opener needs its [language] group (possibly empty), so that
# words such as bytecode:: are not taken for a block.
_DIRECTIVE_START = r'(?<![`:])'

# Code blocks, extracted first.
CODE_BLOCK       = re.compile(
    _DIRECTIVE_START + r'code::(?P<header>\[(?!-\])[^\[\]\n]*\]'
    r'(?:\([^()\n]*\)|\[[^\[\]\n]*\]|\{[^{}\n]*\})*)'
    r'(?P<body>.*?)code::\[-\]', re.DOTALL)
BLOCKS           = re.compile(f'(?P<code>{CODE_BLOCK.pattern})', re.DOTALL)

# Zones that are never transformed by LHTML. They are matched by a single
# regex so that the leftmost zone wins: `<script>` in inline code is code,
# a backquote inside an HTML attribute belongs to the tag, etc.
# Mathematics: \[ display \] and \( inline \); a $ is text
MATH             = re.compile(r'\\\[.+?\\\]|\\\(.+?\\\)', re.DOTALL)
# HTML attributes may span lines; quoted values may contain < or >.
_HTML_ATTRIBUTE = r"[A-Za-z_:][\w:.-]*(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s<>\"'=\x60]+))?"
HTML_TAG = re.compile(r'</?[A-Za-z][\w:-]*(?:\s+' + _HTML_ATTRIBUTE + r')*\s*/?>')
# URL of link::, img::, video::, videoplay:: (parentheses are kept when they
# are not a (.class #id) group, e.g. Mercury_(planet) or fig(1).png)
# Quoted strings can contain the Jinja closing delimiter itself. A quote can
# only start a string (otherwise an unclosed {{ backtracks exponentially),
# and a new opening delimiter ends the search (an unclosed {{ does not scan
# the rest of the document).
_JINJA_STRING = r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')"
_JINJA_EXPRESSION = r'\{\{(?:' + _JINJA_STRING + r'|(?!\}\}|\{\{)[^"\'])*?\}\}'
JINJA = (r'\{#.*?#\}'
         r'|' + _JINJA_EXPRESSION +
         r'|\{%(?:' + _JINJA_STRING + r'|(?!%\}|\{%)[^"\'])*?%\}')
JINJA_RE = re.compile(JINJA, re.DOTALL)
URL_TAGS         = ('link', 'img', 'video', 'videoplay')
# A URL may contain Jinja expressions (img::{{ base }}/photo.jpg)
URL_TOKEN        = (r'(?:' + _JINJA_EXPRESSION +
                    r'|[^\s\[\](){}<>"`\x00]|\((?![.#])[^\s()\[\]{}<>"`\x00]*\))+')
PROTECTED        = re.compile(
    r'(?P<jinja>' + JINJA + r')'
    r'|(?P<comment><!--.*?-->)'
    r'|(?P<raw><(?i:(?P<rawtag>script|style))\b[^>]*>.*?</(?i:(?P=rawtag))\s*>)'
    r'|`(?P<icode>[^`\n]*)`'
    r'|(?P<urltag>(?<![\w-])(?:' + '|'.join(URL_TAGS) + r')::)(?P<url>' + URL_TOKEN + r')'
    r'|(?P<math>' + MATH.pattern + r')'
    r'|(?P<tag>' + HTML_TAG.pattern + r')',
    re.DOTALL)

# One left-to-right pass: an outer protected zone owns its contents.
PROTECTED_BLOCKS = re.compile(BLOCKS.pattern + '|' + PROTECTED.pattern, re.DOTALL)

# Line breaks option: elements that make a line part of the structure
BLOCK_TAGS       = frozenset((
    'div p h1 h2 h3 h4 h5 h6 ul ol li dl dt dd table thead tbody tfoot tr td th '
    'pre blockquote section article header footer nav aside main figure figcaption '
    'hr br source track details summary form').split())
LEADING_TAG      = re.compile(r'^\s*</?([A-Za-z][\w-]*)')
TRAILING_TAG     = re.compile(r'</?([A-Za-z][\w-]*)(?:[^<>"\']|"[^"]*"|\'[^\']*\')*/?>\s*$')
LEADING_PLACEHOLDER  = re.compile(r'^\s*\x00([A-Z])(\d+)\x00')
TRAILING_PLACEHOLDER = re.compile(r'\x00([A-Z])(\d+)\x00\s*$')
JINJA_LINE       = re.compile(r'\s*(\{%.*%\}|\{#.*#\})\s*', re.DOTALL)
# <pre> and <textarea> keep their line breaks: no <br> inside
PREFORMATTED_TAG = re.compile(r'<(/?)(?i:pre|textarea)(?=[\s/>])')
BLOCK_RAW        = re.compile(r'\s*(<!--|<(?i:script|style)\b|\\\[)')

# Placeholders for protected content. They contain no LHTML syntax
# characters, so no processing step can alter them. Kinds:
#   C code block, R raw zone (HTML, math), I inline code, U URL, A attributes
PLACEHOLDER_CHAR = '\x00'
PLACEHOLDER      = re.compile(r'\x00([A-Z])(\d+)\x00')


# ---------------------------------------------------------------------------
# Generic regex transform utility
# ---------------------------------------------------------------------------

def make_placeholder(kind: str, idx: int) -> str:
    """Return the placeholder for entry `idx` of the store `kind` (one uppercase letter)."""
    return f'{PLACEHOLDER_CHAR}{kind}{idx}{PLACEHOLDER_CHAR}'


def restore_from_index(text: str, kind: str, store: list,
                       render_fn: Callable[[object], str] | None = None) -> str:
    """Replace the placeholders of kind `kind` by their stored content.

    If given, `render_fn(entry)` produces the replacement of a stored entry.
    Restoration is recursive: protected content may itself contain
    placeholders of the same kind.
    """
    def _restore(m):
        idx = int(m.group(2))
        if m.group(1) != kind or idx >= len(store):
            return m.group(0)
        entry = store[idx]
        return restore_from_index(render_fn(entry) if render_fn else entry, kind, store, render_fn)
    return regex_transform(text, PLACEHOLDER, _restore)


def regex_transform(text: str, pattern: re.Pattern, transform_fn: Callable[[re.Match], str]) -> str:
    """Apply a regex-based transformation across text.

    For each match of `pattern` in `text`, calls `transform_fn(match)`
    to produce the replacement string. Non-matching text passes through.

    Used to restore the placeholders (restore_from_index).
    """
    parts = []
    prev = 0
    for m in pattern.finditer(text):
        parts.append(text[prev:m.start()])
        parts.append(transform_fn(m))
        prev = m.end()
    parts.append(text[prev:])
    return ''.join(parts)
