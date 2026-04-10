"""Structured error types for LHTML parsing.

These exceptions carry source location information to help
users diagnose problems in their LHTML markup.
"""


class LHTMLError(Exception):
    """Base class for all LHTML errors."""

    def __init__(self, message: str, source_pos: int = -1, source_line: int = -1):
        self.source_pos = source_pos
        self.source_line = source_line
        if source_line >= 0:
            full_message = f'Line {source_line}: {message}'
        elif source_pos >= 0:
            full_message = f'Position {source_pos}: {message}'
        else:
            full_message = message
        super().__init__(full_message)


class LHTMLParseError(LHTMLError):
    """Error during parsing of LHTML markup (unclosed brackets, etc.)."""
    pass


class LHTMLFileNotFound(LHTMLError):
    """An include:: directive references a file that cannot be found."""

    def __init__(self, filename: str, directories: list[str], source_pos: int = -1, source_line: int = -1):
        self.filename = filename
        self.directories = directories
        message = f'Could not find file [{filename}] in directories {directories}'
        super().__init__(message, source_pos, source_line)


class LHTMLTagStackError(LHTMLError):
    """A closing :: tag has no matching opening tag."""

    def __init__(self, source_pos: int = -1, source_line: int = -1):
        message = 'Closing tag :: has no matching opening tag'
        super().__init__(message, source_pos, source_line)


class LHTMLIncludeLoopError(LHTMLError):
    """Too many include iterations — likely a circular include."""

    def __init__(self, max_iterations: int = 20):
        message = f'Too many include iterations (>{max_iterations}), possible circular include'
        super().__init__(message)


def pos_to_line(text: str, pos: int) -> int:
    """Convert a character position to a 1-based line number."""
    if pos < 0 or pos > len(text):
        return -1
    return text[:pos].count('\n') + 1
