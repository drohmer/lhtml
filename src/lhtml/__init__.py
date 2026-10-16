"""LHTML — Lightweight HTML markup language.

A simple markup language that extends HTML with shorthand syntax
for styling, layout, and content formatting.

Usage:
    import lhtml
    html = lhtml.run(text)
    html = lhtml.run(text, {'wrap-auto': True, 'title': 'My Page'})
"""

__version__ = '3.0.0'

from .errors import (
    LHTMLError, LHTMLParseError,
    LHTMLTagStackError, LHTMLWarning, LHTMLMacroError,
)

from .pipeline import ProcessingPipeline, tag_registry, lexer_registry
from .macros import describe_macro, load_macros, register_macros, registry_with_macros


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_pipeline = ProcessingPipeline()


def run(text, meta_arg=None):
    """Process LHTML text and return HTML.

    Args:
        text: LHTML markup string.
        meta_arg: Optional dict overriding default configuration.
            Keys: wrap-auto, title, css, js, line-breaks, macros, current_directory
            (where relative macro files are read from), media (a callable:
            media(src) -> [(url, mime type)], the sources of a video).
            LHTML reads no file but the macro files named here, and no
            front matter: its options come from the caller only.

    Returns:
        HTML string.
    """
    return _pipeline.run(text, meta_arg)


def main():
    """CLI entry point (delegates to cli.main)."""
    from .cli import main as _cli_main
    _cli_main()


__all__ = [
    '__version__', 'run', 'main',
    # Pipeline & plugins
    'ProcessingPipeline', 'tag_registry', 'lexer_registry',
    'describe_macro', 'load_macros', 'register_macros', 'registry_with_macros',
    # Errors
    'LHTMLError', 'LHTMLParseError',
    'LHTMLTagStackError', 'LHTMLWarning', 'LHTMLMacroError',
]
