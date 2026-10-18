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
from collections.abc import Mapping

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

# the same for every lexer; a tab kept (the code of a block is written as it is)
LEXER_OPTIONS = dict(stripall=False, stripnl=True, ensurenl=True, encoding='utf-8')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def checked_lexers(lexers):
    """The lexers of a call, {name: lexer class}, checked (TypeError)."""
    if lexers is None:
        return {}
    if not isinstance(lexers, Mapping) or not all(isinstance(name, str) and isinstance(lexer, type)
                                                  and issubclass(lexer, pygments.lexer.Lexer)
                                                  for name, lexer in lexers.items()):
        raise TypeError(f'lexers: expected a mapping of names to lexer classes, got {lexers!r}')
    return lexers


def _lexer(language, lexers=None):
    """The lexer of a language name: those of the call (`lexers`), then
    LEXERS, then Pygments; None if none knows it."""
    language = (language or '').strip()
    for table in (lexers or {}, LEXERS):
        lexer_class = table.get(language) or next(
            (lexer for name, lexer in table.items() if name.lower() == language.lower()), None)
        if lexer_class is not None:            # any case: MyPy is mypy
            return lexer_class(**LEXER_OPTIONS)
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


def known_language(language, lexers=None):
    return _lexer(language, lexers) is not None


def unknown_language_message(language, lexers=None):
    language = language.strip()
    known = frozenset(LEXERS) | frozenset(lexers or ())
    return f'code::[{language}]: unknown language, shown as plain text{_closest(language.lower(), known)}'


@functools.lru_cache(maxsize=256)
def _closest(language, lexers):
    """The suggestion for an unknown language, sought once per name."""
    return suggestion(language, lexers | _pygments_names())


@functools.cache
def _pygments_names():
    """The names of the languages Pygments knows (its aliases)."""
    return frozenset(alias for _, aliases, _, _ in pygments.lexers.get_all_lexers() for alias in aliases)


def highlight(code: str, language: str, *, lexers: Mapping[str, type] | None = None) -> str:
    """The HTML of a code block, `<div class="code"><pre>...`, highlighted by
    Pygments (`lexers` {name: lexer class} first, then lhtml.LEXERS). An
    unknown language is plain text (parse warns where the block is)."""
    lexer = _lexer(language, checked_lexers(lexers)) or TextLexer(**LEXER_OPTIONS)
    return pygments.highlight(code, lexer, HtmlFormatter(linenos=False, cssclass='code'))
