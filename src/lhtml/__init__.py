"""LHTML — Lightweight HTML markup language.

A simple markup language that extends HTML with shorthand syntax
for styling, layout, and content formatting.

Usage:
    import lhtml
    html = lhtml.run(text)
    html = lhtml.run(text, {'wrap-auto': True, 'title': 'My Page'})

run(text, meta, tags) is documented in pipeline.py.
"""

__version__ = '3.0.0'

from .errors import (
    LHTMLError, LHTMLParseError,
    LHTMLWarning, LHTMLMacroError,
)

from .code import LEXERS
from .export_html import TAGS
from .macros import describe_macro, load_macros, registry_with_macros
from .pipeline import run


def main():
    """CLI entry point (delegates to cli.main)."""
    from .cli import main as _cli_main
    _cli_main()


__all__ = [
    '__version__', 'run', 'main', 'TAGS', 'LEXERS',
    'describe_macro', 'load_macros', 'registry_with_macros',
    # Errors
    'LHTMLError', 'LHTMLParseError',
    'LHTMLWarning', 'LHTMLMacroError',
]
