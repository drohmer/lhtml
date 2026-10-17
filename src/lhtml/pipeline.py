"""The run of LHTML: the text parsed into a document tree, and rendered
(lhtml/tree.py).

Content that must not be transformed (code, raw HTML, math, inline code)
is a leaf of the tree, never read as LHTML; headings, lists, bold, italic
and the :: elements are its nodes.
"""

import os

from .tree import ProcessingContext, parse, render


def run(text, meta=None, tags=None):
    """Convert LHTML text to HTML.

    meta: the options - wrap-auto, title, css, js, line-breaks, macros (a
        mapping, a YAML file relative to current_directory, or a list of
        them), media (a callable: media(src) -> [(url, mime type)], the
        sources of a video). LHTML reads no file but these macro files.
    tags: custom tags {name: lhtml.Tag}, added to the built-in TAGS.

    The problems found are LHTMLWarning warnings and LHTMLError errors, with
    the `line` and `column` in `text` where they are (None if not known).
    """
    meta = dict(meta or {})
    media = meta.get('media')
    if media is not None and not callable(media):
        raise TypeError(f'meta "media" must be callable, got {type(media).__name__}')
    macros = meta.get('macros')
    if macros:
        directory = str(meta.get('current_directory') or '')
        macros = [m if not isinstance(m, str) or os.path.isabs(m) else os.path.join(directory, m)
                  for m in (macros if isinstance(macros, (list, tuple)) else [macros])]
    document = parse(text, tags=tags, macros=macros, context=ProcessingContext(meta, media))
    return render(document, meta, media)
