"""Code block syntax highlighting for LHTML, with Pygments.

LEXERS maps a language name to a Pygments lexer class, taken before the
lexers of Pygments: add one with lhtml.LEXERS['name'] = LexerClass.
"""

from __future__ import annotations


from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.util import ClassNotFound
from pygments.formatters import HtmlFormatter
from pygments.lexer import words, inherit
import functools

import pygments.lexers

from .errors import suggestion


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
    lexer_class = _pygments_lexer(language)
    return lexer_class(**LEXER_OPTIONS) if lexer_class is not None else None


@functools.lru_cache(maxsize=256)
def _pygments_lexer(language):
    """The lexer class Pygments has for a name, None if it has none (looked
    up once per name: Pygments reads every lexer to say it has none)."""
    try:
        return type(get_lexer_by_name(language))
    except ClassNotFound:
        return None


def known_language(language):
    return _lexer(language) is not None


def unknown_language_message(language):
    language = language.strip()
    return f'code::[{language}]: unknown language, shown as plain text{_closest(language.lower(), frozenset(LEXERS))}'


@functools.lru_cache(maxsize=256)
def _closest(language, lexers):
    """The suggestion for an unknown language, sought once per name."""
    return suggestion(language, lexers | _pygments_names())


@functools.cache
def _pygments_names():
    """The names of the languages Pygments knows (its aliases)."""
    return frozenset(alias for _, aliases, _, _ in pygments.lexers.get_all_lexers() for alias in aliases)


def highlight(code: str, language: str) -> str:
    """The HTML of a code block, `<div class="code"><pre>...`, highlighted by
    Pygments (lhtml.LEXERS first). An unknown language is plain text (parse
    warns where the block is)."""
    lexer = _lexer(language) or TextLexer(**LEXER_OPTIONS)
    return pygments.highlight(code, lexer, HtmlFormatter(linenos=False, cssclass='code'))
