"""The run of LHTML: the text parsed into a document tree, and rendered
(lhtml/tree.py).

Content that must not be transformed (code, raw HTML, math, inline code)
is a leaf of the tree, never read as LHTML; headings, lists, bold, italic
and the :: elements are its nodes.
"""

import os
import warnings

from collections.abc import Mapping

from .errors import LHTMLWarning
from .tree import _render, parse, render


# The options run reads; a tag of the caller may read others in context.meta
OPTIONS = ('wrap-auto', 'line-breaks', 'title', 'css', 'js', 'current_directory', 'media', 'macros')


def _spelling(key):
    return str(key).lower().replace('_', '-')


def _check_keys(meta, stacklevel=3):
    """A key written as an option is, but spelled otherwise (line_breaks,
    Wrap-Auto), is not read: a warning names the option. Other keys are the
    caller's (its tags read them)."""
    known = {_spelling(option): option for option in OPTIONS}
    for key in meta:
        option = known.get(_spelling(key))
        if option is not None and key != option:
            warnings.warn(LHTMLWarning(f'option {key!r} is not read: did you mean {option!r}?'),
                          stacklevel=stacklevel)


def run(text, meta=None, tags=None):
    """Convert LHTML text to HTML.

    meta: the options - wrap-auto, title, css, js, line-breaks, macros (a
        mapping, a YAML file relative to current_directory, or a list of
        them), media (a callable: media(src) -> [(url, mime type)], the
        sources of a video). LHTML reads no file but these macro files.
    tags: custom tags {name: lhtml.Tag}, added to the built-in TAGS and the
        macros (a tag given wins).

    The problems found are LHTMLWarning warnings and LHTMLError errors, with
    the `line` and `column` in `text` where they are (None if not known).
    """
    if meta is not None and not isinstance(meta, Mapping):
        raise TypeError(f'meta: expected a mapping of options, got {type(meta).__name__}')
    meta = dict(meta or {})          # its keys are checked by render (_check_keys)
    macros = meta.get('macros')
    if macros:
        directory = str(meta.get('current_directory') or '')
        macros = [m if not isinstance(m, str) or os.path.isabs(m) else os.path.join(directory, m)
                  for m in (macros if isinstance(macros, (list, tuple)) else [macros])]
    document = parse(text, tags=tags, macros=macros)
    return _render(document, meta)
