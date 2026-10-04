"""LHTML — Lightweight HTML markup language.

A simple markup language that extends HTML with shorthand syntax
for styling, layout, and content formatting.

Usage:
    import lhtml
    html = lhtml.run(text)
    html = lhtml.run(text, {'wrap-auto': True, 'title': 'My Page'})
"""

__version__ = '2.5.0'

from .element_extract import extract_bracket_elements
from .insert_in_text import insert_element_from_index, remove_element_to_index
from .wrap_html import wrap_auto

from .process import (
    process_yaml, process_verbatim_to_index, process_verbatim_back_from_index,
    process_remove_comment, process_include, process_include_recursive, find_file,
    process_protect, process_unprotect, process_line_breaks,
    process_bold, process_italic, process_code_inline,
    process_title, process_tag, process_code,
    process_listing,
)

from .errors import (
    LHTMLError, LHTMLParseError, LHTMLFileNotFound,
    LHTMLTagStackError, LHTMLIncludeLoopError, LHTMLWarning, LHTMLMacroError,
)

from .pipeline import ProcessingPipeline, tag_registry, lexer_registry
from .macros import describe_macro, load_macros, register_macros, registry_with_macros


# ---------------------------------------------------------------------------
# Public API (backward-compatible with the old lhtml.py module)
# ---------------------------------------------------------------------------

_pipeline = ProcessingPipeline()


def run(text, meta_arg=None):
    """Process LHTML text and return HTML.

    Args:
        text: LHTML markup string.
        meta_arg: Optional dict overriding default configuration.
            Keys: wrap-auto, title, css, js, directory_include, macros, etc.

    Returns:
        HTML string.
    """
    return _pipeline.run(text, meta_arg)


def analyse_tag(text_in):
    """Parse a single :: tag expression (utility)."""
    return extract_bracket_elements(text_in, text_in.find('::') + 2)


def read_yaml(text_in):
    """Extract YAML front matter from text (utility)."""
    _, yaml_parameter = process_yaml(text_in)
    return yaml_parameter


def main():
    """CLI entry point (delegates to cli.main)."""
    from .cli import main as _cli_main
    _cli_main()


__all__ = [
    # Core API
    '__version__', 'run', 'analyse_tag', 'read_yaml', 'main',
    # Processing functions
    'extract_bracket_elements',
    'process_yaml', 'process_verbatim_to_index', 'process_verbatim_back_from_index',
    'process_remove_comment', 'process_include', 'process_include_recursive', 'find_file',
    'process_protect', 'process_unprotect', 'process_line_breaks',
    'process_bold', 'process_italic', 'process_code_inline',
    'process_title', 'process_tag', 'process_code',
    'process_listing',
    'insert_element_from_index', 'remove_element_to_index',
    'wrap_auto',
    # Pipeline & plugins
    'ProcessingPipeline', 'tag_registry', 'lexer_registry',
    'describe_macro', 'load_macros', 'register_macros', 'registry_with_macros',
    # Errors
    'LHTMLError', 'LHTMLParseError', 'LHTMLFileNotFound',
    'LHTMLTagStackError', 'LHTMLIncludeLoopError', 'LHTMLWarning', 'LHTMLMacroError',
]
