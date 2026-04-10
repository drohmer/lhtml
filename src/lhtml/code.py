"""Code block syntax highlighting for LHTML.

Uses Pygments for highlighting. Custom lexers can be registered
via the lexer_registry in pipeline.py.
"""

from pygments import highlight
from pygments.lexers import get_lexer_by_name
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
    # Check plugin registry first, then built-in lexers
    lexer_class = None
    try:
        from .pipeline import lexer_registry
        lexer_class = lexer_registry.get(language)
    except ImportError:
        pass

    if lexer_class is None:
        lexer_class = _BUILTIN_LEXERS.get(language)

    if lexer_class is not None:
        lexer = lexer_class()
    else:
        lexer = get_lexer_by_name(
            language, stripall=False, stripnl=True,
            ensurenl='True', tabsize=2, encoding='utf-8',
        )

    formatter = HtmlFormatter(linenos=False, cssclass=cssclass)
    return highlight(text, lexer, formatter)
