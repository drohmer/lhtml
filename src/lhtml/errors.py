"""The errors and the warnings of LHTML.

Both carry `line` and `column` (1-based) of the problem in the text given to
`run`, or None where it is not known (a macros file, a text without one),
and `path`: the file it is in when LHTML read one (a macros file), else None.

A message reads `subject: problem[; what to do] (near 'source')`, the
source quoted when the subject does not show it.
"""

import contextvars
import difflib
import warnings

from .patterns import PLACEHOLDER


def suggestion(word, candidates):
    """'; did you mean 'x'?' for the closest of `candidates`, or ''."""
    found = difflib.get_close_matches(word, list(candidates), n=1, cutoff=0.6)
    return f'; did you mean {found[0]!r}?' if found else ''


class _Located:
    def __init__(self, message, line=None, column=None, path=None):
        super().__init__(message)
        self.line, self.column, self.path = line, column, path


class LHTMLError(_Located, Exception):
    """Base class for all LHTML errors. Raised by parse, `problems` holds
    the LHTMLWarning found before it."""
    problems = ()


class LHTMLParseError(LHTMLError):
    """Error during parsing of LHTML markup (unclosed brackets, removed syntax)."""


class LHTMLMacroError(LHTMLError):
    """Invalid macro definition (name, fields or macros file)."""


class LHTMLWarning(_Located, UserWarning):
    """Category of the warnings emitted while processing LHTML markup."""


# The problems of the parse running in this context (a thread, a task): each
# parse has its own list, no global state is changed (warnings.catch_warnings is)
PROBLEMS = contextvars.ContextVar('lhtml_problems', default=None)


def warn(message, place, stacklevel=3):
    """A problem at `place`: (line, column), or an element (or Written) with
    them. Kept by the parse running (PROBLEMS), a warning outside one."""
    if hasattr(place, 'line'):
        place = place.line, place.column
    problem = LHTMLWarning(message, *(place or (None, None)))
    problems = PROBLEMS.get()
    if problems is None:
        warnings.warn(problem, stacklevel=stacklevel)
    else:
        problems.append(problem)


def quote(text, start, end, max_len=40):
    """Short excerpt of the source around a tag, for warning messages."""
    excerpt = PLACEHOLDER.sub('…', text[start:min(end, start + max_len)])
    return excerpt.split('\n')[0]
