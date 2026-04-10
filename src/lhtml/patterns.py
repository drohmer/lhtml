"""Centralized regex patterns and text transformation utilities for LHTML."""

import re
from typing import Callable


# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

YAML_FRONTMATTER = re.compile(r'^---\n(.*?)\n---$', re.DOTALL | re.MULTILINE)
VERBATIM_BLOCK   = re.compile(r'verbatim::\[\](.*?)verbatim::\[-\]', re.DOTALL | re.MULTILINE)
VERBATIM_INDEX   = re.compile(r'verbatim::\[(.*?)\]')
CODE_BLOCK       = re.compile(r'code::(.*?)code::\[-\]', re.DOTALL | re.MULTILINE)
CODE_INDEX       = re.compile(r'code::\[(.*?)\]')
HEADING          = re.compile(r'^(=+)(?:\((.*?)\))? (.*?)$', re.MULTILINE)
BOLD             = re.compile(r'\*\*(.*?)\*\*')
ITALIC           = re.compile(r'__(.*?)__')
INLINE_CODE      = re.compile(r'`(.*?)`')
COMMENT          = re.compile(r'::#(.*?)$', re.MULTILINE)
INCLUDE          = re.compile(r'include::')
TAG_MARKER       = re.compile(r'::')
LIST_ITEM        = re.compile(r'^(\*+) (.*)')

# String constants
VERBATIM_OPEN  = 'verbatim::[]'
VERBATIM_CLOSE = 'verbatim::[-]'
CODE_CLOSE     = 'code::[-]'
SPACER_TAG     = 'nl'

MAX_INCLUDE_ITERATIONS = 20


# ---------------------------------------------------------------------------
# Generic regex transform utility
# ---------------------------------------------------------------------------

def store_to_index(text: str, pattern: re.Pattern | str, name: str, store: list) -> str:
    """Extract regex matches into a store, replacing with indexed placeholders.

    Each match is stored in `store` and replaced with `name::[index]`.
    Used to protect code/verbatim blocks from further processing.
    """
    if isinstance(pattern, str):
        pattern = re.compile(pattern, re.DOTALL | re.MULTILINE)
    parts = []
    prev = 0
    for m in pattern.finditer(text):
        idx = len(store)
        store.append(m.group(0))
        parts.append(text[prev:m.start()])
        parts.append(f'{name}::[{idx}]')
        prev = m.end()
    parts.append(text[prev:])
    return ''.join(parts)


def restore_from_index(text: str, pattern: re.Pattern | str, store: list) -> str:
    """Restore indexed placeholders from a store.

    Matches `name::[index]` patterns and replaces with the stored content.
    """
    if isinstance(pattern, str):
        pattern = re.compile(pattern)
    parts = []
    prev = 0
    for m in pattern.finditer(text):
        idx = int(m.group(1))
        parts.append(text[prev:m.start()])
        parts.append(store[idx])
        prev = m.end()
    parts.append(text[prev:])
    return ''.join(parts)


def regex_transform(text: str, pattern: re.Pattern, transform_fn: Callable[[re.Match], str]) -> str:
    """Apply a regex-based transformation across text.

    For each match of `pattern` in `text`, calls `transform_fn(match)`
    to produce the replacement string. Non-matching text passes through.

    This eliminates the boilerplate loop duplicated across process_bold,
    process_italic, process_code_inline, process_title, etc.
    """
    parts = []
    prev = 0
    for m in pattern.finditer(text):
        parts.append(text[prev:m.start()])
        parts.append(transform_fn(m))
        prev = m.end()
    parts.append(text[prev:])
    return ''.join(parts)
