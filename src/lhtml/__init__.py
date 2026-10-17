"""LHTML — Lightweight HTML markup language.

A simple markup language that extends HTML with shorthand syntax
for styling, layout, and content formatting.

Usage:
    import lhtml
    html = lhtml.run(text)
    html = lhtml.run(text, macros=lhtml.load_macros('macros.yaml'), line_breaks=True)
    page = lhtml.wrap(html, title='My Page', css=['style.css'])
    document = lhtml.parse(text)          # the document tree (tree.py)
    html = lhtml.render(document)

run is documented in pipeline.py.
"""

__version__ = '3.0.0'

from .errors import (
    LHTMLError, LHTMLParseError,
    LHTMLWarning, LHTMLMacroError,
)

from .code import LEXERS
from .export_html import TAGS, Tag
from .macros import describe_macro, load_macros, registry_with_macros
from .pipeline import run
from .tree import parse, render
from .wrap_html import wrap


def main():
    """CLI entry point (delegates to cli.main)."""
    from .cli import main as _cli_main
    _cli_main()


__all__ = [
    '__version__', 'run', 'parse', 'render', 'wrap', 'main', 'TAGS', 'Tag', 'LEXERS',
    'describe_macro', 'load_macros', 'registry_with_macros',
    # Errors
    'LHTMLError', 'LHTMLParseError',
    'LHTMLWarning', 'LHTMLMacroError',
]
