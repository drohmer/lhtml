"""The problems of a conversion as the CLI shows them, apart from the parser:
a Diagnostic (where, what), then its text for a terminal or for a log.

In a terminal (stderr is one), the line follows, the place underlined
(what the message quoted with `near` is there, so the quote goes), and a
blank line ends each diagnostic:

    page.l.html:3:1: warning: div:: is never closed
      3 │ div::(.note)
        │ ^^^^^^^^^^^^


Elsewhere (a file, a pipe, an editor), one line:

    page.l.html:3:1: warning: div:: is never closed (near 'div::(.note)')

The level is always written: the color is never needed. Colors follow
NO_COLOR, FORCE_COLOR and TERM=dumb.
"""

from __future__ import annotations

import codecs
import os
import re
import unicodedata
from dataclasses import dataclass

_EXCERPT = 100                  # columns of a line shown around the place

_COLORS = {'error': '1;31', 'warning': '1;33', 'note': '1;36', 'dim': '2', 'bold': '1', 'done': '1;32'}
# the quote of a message, shown by the excerpt: (near '...') or near '...' at its end
_NEAR = re.compile(r" \(near '[^\n]*'\)$| near '[^\n]*'$")


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
        try:
            relative = os.path.relpath(path)
        except ValueError:              # another drive (Windows): no relative path
            return path
        if relative != os.pardir and not relative.startswith(os.pardir + os.sep):     # not ..x.l.html
            return relative
    return path


def _width(ch):
    if len(ch) != 1:                    # an escape: \xe9
        return len(ch)
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in 'WF' else 1


def _blank(text, show):
    """Spaces as wide as the text (its tabs kept: they align the same)."""
    return ''.join('\t' if ch == '\t' else ' ' * _width(show(ch)) for ch in text)


def _marks(text, show):
    return ''.join('^' * _width(show(ch)) if ch != '\t' else '^^^^' for ch in text) or '^'


def excerpt(source_line, column, show=lambda ch: ch):
    """(the line, its underline) for a column (1-based): the word at the
    column underlined, the line cut around it when it is long. `show(ch)`:
    how a character is written (an escape, where the stream cannot)."""
    line = source_line.rstrip('\n')
    at = max(0, min(column - 1, len(line)))

    def width(ch):                      # its columns, as shown
        return 4 if ch == '\t' else _width(show(ch))
    total = 0
    for ch in line:                     # its width, up to what is shown (a long line: read around the place only)
        total += width(ch)
        if total > _EXCERPT:
            break
    start, stop, before, after = 0, len(line), '', ''
    if total > _EXCERPT:                # cut around the place: a third before it, by columns
        start, used = at, 0
        while start > 0 and used + width(line[start - 1]) <= _EXCERPT // 3:
            start -= 1
            used += width(line[start])
        stop, used = start, 0
        while stop < len(line) and used + width(line[stop]) <= _EXCERPT:
            used += width(line[stop])
            stop += 1
        before = '…' if start else ''
        after = '…' if stop < len(line) else ''
    end = at
    while end < stop and not line[end].isspace():
        end += 1
    end = max(at + 1, end) if at < len(line) else at
    shown = show(before) + ''.join(show(ch) for ch in line[start:stop]) + show(after)
    underline = _blank(before + line[start:at], show) + _marks(line[at:end], show)
    return shown, underline


class Reporter:
    """Writes the diagnostics on a stream (stderr): with an excerpt and
    colors in a terminal, one line each elsewhere."""

    def __init__(self, stream, rich=None, color=None):
        self.stream = stream            # None (a closed stderr): nothing is written
        terminal = _isatty(stream)
        self.rich = terminal if rich is None else rich
        self.color = _color(terminal) if color is None else color
        encoding = getattr(stream, 'encoding', None) or ''
        try:
            encoding = codecs.lookup(encoding).name if encoding else ''     # iso8859-1, koi8-r
        except LookupError:
            encoding = 'ascii'          # an encoding Python does not know: what any can write
        self.unicode = encoding.startswith('utf')
        self.encoding = encoding        # '': a stream of str (no encoding to respect)
        self.counts = {'error': 0, 'warning': 0}
        self._split = None              # (a source, its lines): the last one reported

    def paint(self, text, style):
        return f'\x1b[{_COLORS[style]}m{text}\x1b[0m' if self.color and text else text

    def symbol(self, fancy, plain):
        return fancy if self.unicode else plain

    def report(self, diagnostic, source=None):
        """Writes a diagnostic; `source`: the text it is in (its excerpt)."""
        self.counts[diagnostic.level] = self.counts.get(diagnostic.level, 0) + 1
        level = self.paint(diagnostic.level, diagnostic.level if diagnostic.level in _COLORS else 'bold')
        lines = self._lines(source) if self.rich and source is not None and diagnostic.line else []
        if diagnostic.line and diagnostic.line <= len(lines):
            line = lines[diagnostic.line - 1]
            near = _NEAR.search(diagnostic.message)
            quote = near and near.group(0).split("'", 1)[1].rsplit("'", 1)[0]
            # the quote goes when the excerpt shows it (not a place on another line)
            message = _NEAR.sub('', diagnostic.message) if near and quote.rstrip('…') in line \
                else diagnostic.message
            shown, underline = excerpt(line, diagnostic.column or 1, self._show)
            number = str(diagnostic.line)
            bar = self.paint(self.symbol('│', '|'), 'dim')
            self.write(f'{self.paint(diagnostic.place, "bold")}: {level}: {message}')
            self.write(f'  {self.paint(number, "dim")} {bar} {shown}')
            self.write(f'  {" " * len(number)} {bar} {self.paint(underline, diagnostic.level)}')
            self.write('')
        else:
            self.write(f'{self.paint(diagnostic.place, "bold")}: {level}: {diagnostic.message}')

    def _lines(self, source):
        """The lines of a source, split once for all its diagnostics."""
        if self._split is None or self._split[0] is not source:
            self._split = (source, source.split('\n'))
        return self._split[1]

    def summary(self, converted, failed):
        """`2 converted · 1 failed · 3 warnings`, each count in its color."""
        parts = [self.paint(f'{converted} converted', 'done' if converted and not failed else 'bold')]
        if failed:
            parts.append(self.paint(f'{failed} failed', 'error'))
        warned = self.counts.get('warning', 0)
        if warned:
            parts.append(self.paint(f'{warned} warning{"s" if warned > 1 else ""}', 'warning'))
        return self.symbol(' · ', ', ').join(parts)

    def _show(self, text):
        """The text as the stream can write it."""
        if self.unicode or not self.encoding:
            return text
        try:
            return text.encode(self.encoding, 'backslashreplace').decode(self.encoding)
        except LookupError:
            return text.encode('ascii', 'backslashreplace').decode('ascii')

    def write(self, text):
        """Writes a line, what the stream cannot encode as escapes (\\xe9):
        a path or a message with an accent is shown on an ASCII stream."""
        if self.stream is None:
            return
        text = self._show(text) + '\n'
        try:
            try:
                self.stream.write(text)
            except UnicodeEncodeError:  # an encoding the stream did not declare
                self.stream.write(text.encode('ascii', 'backslashreplace').decode('ascii'))
            self.stream.flush()
        except (OSError, ValueError):   # a closed stderr: the run goes on
            self.stream = None


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
