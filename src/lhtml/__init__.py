"""LHTML — Lightweight HTML markup language.

A simple markup language that extends HTML with shorthand syntax
for styling, layout, and content formatting.

Usage:
    import lhtml
    html = lhtml.run(text)
    html = lhtml.run(text, macros=lhtml.load_macros('macros.yaml'), line_breaks=True)
    page = lhtml.wrap(html, title='My Page', css=['style.css'])
    document = lhtml.parse(text)          # the document tree: lhtml.Element, lhtml.Text... (nodes.py)
    html = lhtml.render(document)         # its HTML, from the fields of the nodes
    document.problems                     # the LHTMLWarning found (parse(..., warn=False): not warned)
    tags = {'alert': lhtml.Tag(build)}    # build(written) -> nodes: a tag of the caller (docs/advanced.md)

run is documented in pipeline.py.
"""

__version__ = '3.0.0'

from .errors import (
    LHTMLError, LHTMLParseError,
    LHTMLWarning, LHTMLMacroError,
)

from .code import LEXERS, highlight
from .export_html import TAGS, Tag
from .macros import describe_macro, load_macros, registry_with_macros
from .pipeline import run
from .attributes import Attributes
from .nodes import (
    Code, Document, Element, Emphasis, Heading, InlineCode, Item, List, Math, Node, Raw, Strong, Text, Video,
    Written,
)
from .render import render
from .tree import parse
from .wrap_html import wrap


def main():
    """CLI entry point (delegates to cli.main)."""
    from .cli import main as _cli_main
    _cli_main()


__all__ = [
    '__version__', 'run', 'parse', 'render', 'wrap', 'main', 'TAGS', 'Tag', 'LEXERS', 'highlight',
    'describe_macro', 'load_macros', 'registry_with_macros', 'Attributes',
    'Node', 'Document', 'Text', 'Heading', 'List', 'Item', 'Strong', 'Emphasis', 'Element', 'Video',
    'Code', 'InlineCode', 'Math', 'Raw', 'Written',
    # Errors
    'LHTMLError', 'LHTMLParseError',
    'LHTMLWarning', 'LHTMLMacroError',
]
