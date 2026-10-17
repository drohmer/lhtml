"""The errors and the warnings of LHTML."""


class LHTMLError(Exception):
    """Base class for all LHTML errors."""


class LHTMLParseError(LHTMLError):
    """Error during parsing of LHTML markup (unclosed brackets, removed syntax)."""


class LHTMLMacroError(LHTMLError):
    """Invalid macro definition (name, fields or macros file)."""


class LHTMLWarning(UserWarning):
    """Category of the warnings emitted while processing LHTML markup."""
