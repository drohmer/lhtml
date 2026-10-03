"""Processing pipeline and tag handler registry for LHTML.

The pipeline orchestrates the multi-pass LHTML-to-HTML transformation.
Tag handlers are registered in a plugin registry, making it easy to
add custom element types (e.g., new :: tag names) without modifying
the core processing code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

META_DEFAULTS = {
    'wrap-auto': False,
    'add_title_id': False,
    'title': 'Webpage',
    'css': [],
    'js': [],
    'wrap-custom-pre': '',
    'wrap-custom-post': '',
    'line-breaks': False,
}


def _default_meta():
    """Default configuration (directory_include is evaluated at call time)."""
    return {**META_DEFAULTS, 'directory_include': [os.getcwd() + '/']}


@dataclass
class ProcessingContext:
    """Mutable state carried through the pipeline."""
    text: str
    meta: dict = field(default_factory=dict)
    stores: object = None  # process.ProtectionStores
    current_directory: str = ''


# ---------------------------------------------------------------------------
# Tag handler registry (plugin system)
# ---------------------------------------------------------------------------

# A tag handler receives (element_dict, tag_to_close, current_directory)
# and returns (html_string, is_real_tag).
TagHandler = Callable[[dict, list, str], tuple[str, bool]]


class TagRegistry:
    """Registry for LHTML :: tag element handlers.

    Built-in tags (div, span, link, img, video, videoplay) are
    registered at import time. Users can register custom tags:

        from lhtml.pipeline import tag_registry
        tag_registry.register('custom', my_handler)
    """

    def __init__(self):
        self._handlers: dict[str, TagHandler] = {}

    def register(self, tag_name: str, handler: TagHandler):
        """Register a handler for a tag name."""
        self._handlers[tag_name] = handler

    def get(self, tag_name: str) -> TagHandler | None:
        """Look up the handler for a tag name."""
        return self._handlers.get(tag_name)

    def has(self, tag_name: str) -> bool:
        return tag_name in self._handlers

    def registered_tags(self) -> list[str]:
        return list(self._handlers.keys())


# Global registry instance
tag_registry = TagRegistry()


def _register_builtin_tags():
    """Register the built-in LHTML tag handlers."""
    from .export_html import (
        export_html_generic, export_html_link,
        export_html_img, export_html_video,
    )

    def _handle_generic(tag_name):
        def handler(element, tag_to_close, current_directory):
            return export_html_generic(element, tag_name, tag_to_close), True
        return handler

    tag_registry.register('div', _handle_generic('div'))
    tag_registry.register('span', _handle_generic('span'))

    def _handle_link(element, tag_to_close, current_directory):
        return export_html_link(element), True
    tag_registry.register('link', _handle_link)

    def _handle_img(element, tag_to_close, current_directory):
        return export_html_img(element), True
    tag_registry.register('img', _handle_img)

    def _handle_video(element, tag_to_close, current_directory):
        return export_html_video(element, '', current_directory), True
    tag_registry.register('video', _handle_video)

    def _handle_videoplay(element, tag_to_close, current_directory):
        return export_html_video(element, 'autoplay loop muted', current_directory), True
    tag_registry.register('videoplay', _handle_videoplay)


# ---------------------------------------------------------------------------
# Code lexer registry (plugin system for syntax highlighting)
# ---------------------------------------------------------------------------

class LexerRegistry:
    """Registry for custom Pygments lexers by language name."""

    def __init__(self):
        self._lexers: dict[str, type] = {}

    def register(self, language: str, lexer_class: type):
        self._lexers[language] = lexer_class

    def get(self, language: str) -> type | None:
        return self._lexers.get(language)


lexer_registry = LexerRegistry()

_register_builtin_tags()


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class ProcessingPipeline:
    """Orchestrates the LHTML-to-HTML transformation pipeline.

    Usage:
        pipeline = ProcessingPipeline()
        html = pipeline.run(lhtml_text)
        html = pipeline.run(lhtml_text, meta={'wrap-auto': True})
    """

    def __init__(self, registry: TagRegistry | None = None):
        self.tag_registry = registry or tag_registry

    def run(self, text: str, meta_arg: dict | None = None) -> str:
        from .process import (
            ProtectionStores, process_yaml, process_include_recursive,
            process_unprotect, process_title, process_listing,
            process_bold, process_italic, process_tag,
            render_inline_code, render_code_block, process_line_breaks,
        )
        from .wrap_html import wrap_auto
        from .process import normalize_input

        text = normalize_input(text)
        ctx = ProcessingContext(
            text=text,
            meta={**_default_meta(), **(meta_arg or {})},
            stores=ProtectionStores(),
        )
        stores = ctx.stores

        # Phase 1: YAML front matter
        ctx.text, meta_yaml = process_yaml(ctx.text)
        ctx.meta = {**ctx.meta, **meta_yaml}
        ctx.current_directory = str(ctx.meta.get('current_directory') or '')
        directory_include = ctx.meta.get('directory_include') or []
        if isinstance(directory_include, (str, os.PathLike)):
            directory_include = [directory_include]
        ctx.meta['directory_include'] = [str(d) for d in directory_include]

        # Phase 2: For each file: verbatim/code blocks and protected zones
        # (HTML, inline code, URLs, math) are replaced by placeholders,
        # comments are removed, then includes are expanded (recursive)
        ctx.text = process_include_recursive(ctx.text, ctx.meta['directory_include'], stores)

        # Phase 3: Block-level elements
        ctx.text = process_title(ctx.text)
        ctx.text = process_listing(ctx.text)

        # Phase 4: Inline elements
        ctx.text = process_bold(ctx.text)
        ctx.text = process_italic(ctx.text)

        # Phase 5: Tag elements (uses tag_registry). Inside inline code,
        # only named tags (e.g. link::) are processed.
        def resolve_urls(s):
            return stores.restore(s, 'U')

        ctx.text = process_tag(ctx.text, ctx.current_directory, self.tag_registry,
                               resolve=resolve_urls)
        ctx.text = stores.restore(ctx.text, 'I', lambda content: render_inline_code(
            process_tag(content, ctx.current_directory, self.tag_registry, inline=True)))

        # Optional: source line breaks become <br> (protected zones are
        # still placeholders, so their content is not affected)
        if ctx.meta.get('line-breaks') is True:
            ctx.text = process_line_breaks(ctx.text, stores)

        # Phase 6: Restore protected zones, code blocks (highlighted) and
        # verbatim blocks
        ctx.text = process_unprotect(ctx.text, stores)
        ctx.text = stores.restore(ctx.text, 'C', lambda entry: render_code_block(entry, stores.V))
        ctx.text = stores.restore(ctx.text, 'V')

        # Phase 7: Optional HTML wrapping
        if ctx.meta.get('wrap-auto') is True:
            ctx.text = wrap_auto(ctx.text, ctx.meta)

        return ctx.text
