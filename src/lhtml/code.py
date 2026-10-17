"""Code block syntax highlighting for LHTML, with Pygments.

LEXERS maps a language name to a Pygments lexer class, taken before the
lexers of Pygments: add one with lhtml.LEXERS['name'] = LexerClass.
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


LEXERS = {
    'c++': CppCgpLexer,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_html_code(text, language):
    """Highlight a code block and return HTML."""
    language = (language or '').strip()
    lexer_class = LEXERS.get(language) or LEXERS.get(language.lower())
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

    formatter = HtmlFormatter(linenos=False, cssclass='code')
    return highlight(text, lexer, formatter)
