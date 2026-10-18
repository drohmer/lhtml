"""Code block syntax highlighting for LHTML, with Pygments.

LEXERS maps a language name to a Pygments lexer class, taken before the
lexers of Pygments: add one with lhtml.LEXERS['name'] = LexerClass.
"""

from __future__ import annotations


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

LEXER_OPTIONS = dict(stripall=False, stripnl=True, ensurenl=True, tabsize=2, encoding='utf-8')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _lexer(language):
    """The lexer of a language name, None if neither LEXERS nor Pygments know it."""
    language = (language or '').strip()
    lexer_class = LEXERS.get(language) or LEXERS.get(language.lower())
    if lexer_class is not None:
        return lexer_class()
    if not language:
        return TextLexer(**LEXER_OPTIONS)
    try:
        return get_lexer_by_name(language, **LEXER_OPTIONS)
    except ClassNotFound:
        return None


def known_language(language):
    return _lexer(language) is not None


def unknown_language_message(language):
    return f'Unknown language {language.strip()!r} for code::[...] block, rendered as plain text'


def highlight(code: str, language: str) -> str:
    """The HTML of a code block, `<div class="code"><pre>...`, highlighted by
    Pygments (lhtml.LEXERS first). An unknown language is plain text (parse
    warns where the block is)."""
    lexer = _lexer(language) or TextLexer(**LEXER_OPTIONS)
    return pygments.highlight(code, lexer, HtmlFormatter(linenos=False, cssclass='code'))
