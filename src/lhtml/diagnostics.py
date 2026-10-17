"""The problems of a conversion as the CLI shows them, apart from the parser:
a Diagnostic (where, what), then its text for a terminal or for a log.

In a terminal (stderr is one):

    page.l.html:3:1: warning: div:: is never closed (near 'div::(.note)')
      3 │ div::(.note)
        │ ^^^^^^^^^^^^

Elsewhere (a file, a pipe, an editor), one line:

    page.l.html:3:1: warning: div:: is never closed (near 'div::(.note)')

The level is always written: the color is never needed. Colors follow
NO_COLOR, FORCE_COLOR and TERM=dumb.
"""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass

_EXCERPT = 100                  # columns of a line shown around the place

_COLORS = {'error': '1;31', 'warning': '1;33', 'note': '1;36', 'dim': '2', 'bold': '1'}


@dataclass(frozen=True)
class Diagnostic:
    path: str
    level: str                  # 'error' or 'warning'
    message: str
    line: int | None = None     # 1-based
    column: int | None = None

    @classmethod
    def of(cls, path, level, problem):
        """The diagnostic of an LHTMLError, LHTMLWarning, OSError..."""
        if isinstance(problem, OSError) and problem.strerror:
            message = problem.strerror + (f': {problem.filename}' if problem.filename else '')
        else:
            message = str(problem)
        return cls(path, level, message, getattr(problem, 'line', None), getattr(problem, 'column', None))

    @property
    def place(self):
        """`path:line:column`, as far as it is known."""
        return ':'.join([self.path] + [str(n) for n in (self.line, self.column) if n is not None])


def shown_path(path):
    """A path relative to the current directory when it is inside it."""
    if os.path.isabs(path):
        relative = os.path.relpath(path)
        if not relative.startswith(os.pardir):
            return relative
    return path


def _width(ch):
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in 'WF' else 1


def _blank(text):
    """Spaces as wide as the text (its tabs kept: they align the same)."""
    return ''.join('\t' if ch == '\t' else ' ' * _width(ch) for ch in text)


def _marks(text):
    return ''.join('^' * _width(ch) if ch != '\t' else '^^^^' for ch in text) or '^'


def excerpt(source_line, column):
    """(the line, its underline) for a column (1-based): the word at the
    column underlined, the line cut around it when it is long."""
    line = source_line.rstrip('\n')
    at = max(0, min(column - 1, len(line)))
    end = at
    while end < len(line) and not line[end].isspace():
        end += 1
    start, stop, before, after = 0, len(line), '', ''
    if len(line) > _EXCERPT:
        start = max(0, at - _EXCERPT // 3)
        stop = min(len(line), start + _EXCERPT)
        before = '…' if start else ''
        after = '…' if stop < len(line) else ''
    end = max(at + 1, min(end, stop)) if at < len(line) else at
    shown = before + line[start:stop] + after
    underline = _blank(before + line[start:at]) + _marks(line[at:end])
    return shown, underline


class Reporter:
    """Writes the diagnostics on a stream (stderr): with an excerpt and
    colors in a terminal, one line each elsewhere."""

    def __init__(self, stream, rich=None, color=None):
        self.stream = stream
        terminal = _isatty(stream)
        self.rich = terminal if rich is None else rich
        self.color = _color(terminal) if color is None else color
        encoding = (getattr(stream, 'encoding', None) or '').lower().replace('-', '')
        self.unicode = encoding.startswith('utf')
        self.counts = {'error': 0, 'warning': 0}

    def paint(self, text, style):
        return f'\x1b[{_COLORS[style]}m{text}\x1b[0m' if self.color and text else text

    def symbol(self, fancy, plain):
        return fancy if self.unicode else plain

    def report(self, diagnostic, source=None):
        """Writes a diagnostic; `source`: the text it is in (its excerpt)."""
        self.counts[diagnostic.level] = self.counts.get(diagnostic.level, 0) + 1
        level = self.paint(diagnostic.level, diagnostic.level if diagnostic.level in _COLORS else 'bold')
        self.write(f'{self.paint(diagnostic.place, "bold")}: {level}: {diagnostic.message}')
        if self.rich and source is not None and diagnostic.line:
            lines = source.split('\n')
            if diagnostic.line <= len(lines):
                shown, underline = excerpt(lines[diagnostic.line - 1], diagnostic.column or 1)
                number = str(diagnostic.line)
                bar = self.paint(self.symbol('│', '|'), 'dim')
                self.write(f'  {self.paint(number, "dim")} {bar} {shown}')
                self.write(f'  {" " * len(number)} {bar} {self.paint(underline, diagnostic.level)}')

    def write(self, text):
        self.stream.write(text + '\n')
        self.stream.flush()


def _isatty(stream):
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


def _color(terminal):
    if os.environ.get('NO_COLOR'):
        return False
    if os.environ.get('FORCE_COLOR'):
        return True
    return terminal and os.environ.get('TERM') != 'dumb'
