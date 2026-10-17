"""The errors and the warnings of LHTML.

Both carry `line` and `column` (1-based) of the problem in the text given to
`run`, or None where it is not known (a macros file, a text without one).
"""


class _Located:
    def __init__(self, message, line=None, column=None):
        super().__init__(message)
        self.line, self.column = line, column


class LHTMLError(_Located, Exception):
    """Base class for all LHTML errors."""


class LHTMLParseError(LHTMLError):
    """Error during parsing of LHTML markup (unclosed brackets, removed syntax)."""


class LHTMLMacroError(LHTMLError):
    """Invalid macro definition (name, fields or macros file)."""


class LHTMLWarning(_Located, UserWarning):
    """Category of the warnings emitted while processing LHTML markup."""
