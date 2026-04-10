"""Processing pipeline and tag handler registry for LHTML.

The pipeline orchestrates the multi-pass LHTML-to-HTML transformation.
Tag handlers are registered in a plugin registry, making it easy to
add custom element types (e.g., new :: tag names) without modifying
the core processing code.
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass, field
from typing import Callable

from .errors import LHTMLIncludeLoopError
from .patterns import MAX_INCLUDE_ITERATIONS


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
    'directory_include': [os.getcwd() + '/'],
}


@dataclass
class ProcessingContext:
    """Mutable state carried through the pipeline."""
    text: str
    meta: dict = field(default_factory=dict)
    verbatim_store: list = field(default_factory=list)
    code_store: list = field(default_factory=list)
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
            process_yaml, process_verbatim_to_index,
            process_remove_comment, process_include,
            process_title, process_listing,
            process_bold, process_italic, process_code_inline,
            process_tag, process_code,
            process_verbatim_back_from_index,
        )
        from .wrap_html import wrap_auto
        from .patterns import CODE_BLOCK, CODE_INDEX, store_to_index, restore_from_index

        ctx = ProcessingContext(
            text=text,
            meta={**META_DEFAULTS, **(meta_arg or {})},
        )

        # Phase 1: YAML front matter
        ctx.text, meta_yaml = process_yaml(ctx.text)
        ctx.meta = {**ctx.meta, **meta_yaml}
        ctx.current_directory = ctx.meta.get('current_directory', '')

        # Phase 2: Verbatim / comments / includes (iterative)
        found_include = True
        iteration = 0
        while found_include:
            ctx.text = process_verbatim_to_index(ctx.text, ctx.verbatim_store)
            ctx.text = process_remove_comment(ctx.text)
            ctx.text, found_include = process_include(ctx.text, ctx.meta['directory_include'])
            iteration += 1
            if iteration > MAX_INCLUDE_ITERATIONS:
                warnings.warn(str(LHTMLIncludeLoopError(MAX_INCLUDE_ITERATIONS)))
                break

        # Phase 3: Protect code blocks
        ctx.text = store_to_index(ctx.text, CODE_BLOCK, 'code', ctx.code_store)

        # Phase 4: Block-level elements
        ctx.text = process_title(ctx.text)
        ctx.text = process_listing(ctx.text)

        # Phase 5: Inline elements
        ctx.text = process_bold(ctx.text)
        ctx.text = process_italic(ctx.text)
        ctx.text = process_code_inline(ctx.text)

        # Phase 6: Tag elements (uses tag_registry)
        ctx.text = process_tag(ctx.text, ctx.current_directory, self.tag_registry)

        # Phase 7: Restore code blocks with highlighting
        ctx.text = restore_from_index(ctx.text, CODE_INDEX, ctx.code_store)
        ctx.text = process_code(ctx.text)

        # Phase 8: Restore verbatim blocks
        ctx.text = process_verbatim_back_from_index(ctx.text, ctx.verbatim_store)

        # Phase 9: Optional HTML wrapping
        if ctx.meta.get('wrap-auto') is True:
            ctx.text = wrap_auto(ctx.text, ctx.meta)

        return ctx.text
