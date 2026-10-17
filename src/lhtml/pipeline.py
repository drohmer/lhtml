"""The run of LHTML: the passes that turn LHTML text into HTML.

Content that must not be transformed (code, raw HTML, math, inline code,
URLs, attribute groups) is first replaced by placeholders, the LHTML syntax
around them is converted pass by pass, and the placeholders are restored.
"""

import os
from dataclasses import dataclass
from typing import Callable

from .export_html import TAGS
from .listing import process_listing
from .macros import registry_with_macros
from .process import (
    ProtectionStores, normalize_input, process_prepare, process_unprotect,
    process_title, process_bold, process_italic, process_tag, process_line_breaks,
    render_inline_code, render_code_block,
)
from .wrap_html import wrap_auto


@dataclass
class ProcessingContext:
    """What a tag handler receives as its third argument."""
    meta: dict
    media: Callable | None = None   # media(src) -> [(url, mime)], given by the caller


def run(text, meta=None, tags=None):
    """Convert LHTML text to HTML.

    meta: the options - wrap-auto, title, css, js, line-breaks, macros (a
        mapping, a YAML file relative to current_directory, or a list of
        them), media (a callable: media(src) -> [(url, mime type)], the
        sources of a video). LHTML reads no file but these macro files.
    tags: custom tag handlers {name: handler}, added to the built-in TAGS.
    """
    meta = dict(meta or {})
    media = meta.get('media')
    if media is not None and not callable(media):
        raise TypeError(f'meta "media" must be callable, got {type(media).__name__}')
    handlers = {**TAGS, **(tags or {})}
    macros = meta.get('macros')
    if macros:
        directory = str(meta.get('current_directory') or '')
        macros = [m if not isinstance(m, str) or os.path.isabs(m) else os.path.join(directory, m)
                  for m in (macros if isinstance(macros, (list, tuple)) else [macros])]
        handlers = registry_with_macros(macros, handlers)
    context = ProcessingContext(meta, media)
    stores = ProtectionStores()

    text = process_prepare(normalize_input(text), stores)
    text = process_title(text, stores)
    text = process_listing(text)
    text = process_bold(text)
    text = process_italic(text)
    text = process_tag(text, context, handlers,
                       resolve=lambda s: stores.restore(stores.restore(s, 'A'), 'U'))
    text = stores.restore(text, 'I', render_inline_code)          # inline code is literal
    if meta.get('line-breaks') is True:     # protected zones are still placeholders
        text = process_line_breaks(text, stores)
    text = process_unprotect(text, stores)
    text = stores.restore(text, 'C', render_code_block)
    if meta.get('wrap-auto') is True:
        text = wrap_auto(text, meta)
    return text
