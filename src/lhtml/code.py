"""Code block syntax highlighting for LHTML.

Uses Pygments for highlighting. Custom lexers can be registered
via the lexer_registry in pipeline.py.
"""

import warnings

from pygments import highlight
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.util import ClassNotFound
from pygments.formatters import HtmlFormatter
from pygments.lexer import words, inherit
import pygments.lexers


# ---------------------------------------------------------------------------
# Built-in custom lexer: C++ with CGP library types
# ---------------------------------------------------------------------------

class CppCgpLexer(pygments.lexers.CppLexer):
    """Extended C++ lexer with CGP library types and functions."""
    name = 'C++ (CGP)'
    tokens = {
        'statements': [
            (words((
                'vec2', 'vec3', 'vec4', 'mat2', 'mat3', 'mat4',
                'numarray_stack', 'numarray', 'mesh', 'mesh_drawable',
                'rotation_transform', 'affine_rt', 'affine_rts', 'affine',
                'quaternion', 'string', 'ostream',
            ), suffix=r'\b'), pygments.token.Keyword.Type),
            (words((
                'dot', 'cross', 'norm', 'normalize',
                'draw', 'draw_wireframe', 'transpose', 'det', 'inverse',
            ), suffix=r'\b'), pygments.token.Keyword.Function),
            (r'gl\w*', pygments.token.Keyword.Function),
            (r'const\&', pygments.token.Number),
            (r'std::', pygments.token.Number),
            (r'cgp::', pygments.token.Number),
            inherit,
        ]
    }


# Default custom lexer mapping
_BUILTIN_LEXERS = {
    'c++': CppCgpLexer,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_html_code(text, language, cssclass='code'):
    """Highlight a code block and return HTML."""
    language = (language or '').strip()

    # Check plugin registry first, then built-in lexers (case-insensitive)
    lexer_class = None
    try:
        from .pipeline import lexer_registry
        lexer_class = lexer_registry.get(language) or lexer_registry.get(language.lower())
    except ImportError:
        pass

    if lexer_class is None:
        lexer_class = _BUILTIN_LEXERS.get(language.lower())

    lexer_options = dict(stripall=False, stripnl=True, ensurenl=True,
                         tabsize=2, encoding='utf-8')
    if lexer_class is not None:
        lexer = lexer_class()
    elif not language:
        lexer = TextLexer(**lexer_options)
    else:
        try:
            lexer = get_lexer_by_name(language, **lexer_options)
        except ClassNotFound:
            from .errors import LHTMLWarning
            warnings.warn(f'Unknown language {language!r} for code::[...] block, '
                          'rendered as plain text', LHTMLWarning, stacklevel=2)
            lexer = TextLexer(**lexer_options)

    formatter = HtmlFormatter(linenos=False, cssclass=cssclass)
    return highlight(text, lexer, formatter)
