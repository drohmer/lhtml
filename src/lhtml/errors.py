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


class LHTMLWarning(UserWarning):
    """Category of the warnings emitted while processing LHTML markup."""


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
    """A closing :: tag has no matching opening tag, or a tag is never closed."""

    def __init__(self, context: str | int = '', unclosed: str | None = None,
                 source_pos: int = -1, source_line: int = -1):
        if isinstance(context, int):
            # LHTML 2.2 signature: LHTMLTagStackError(source_pos, source_line)
            if isinstance(unclosed, int):
                source_line, unclosed = unclosed, None
            source_pos, context = context, ''
        self.context = context
        self.unclosed = unclosed
        if unclosed:
            message = f'Tag <{unclosed}> is never closed'
        else:
            message = 'Closing tag :: has no matching opening tag'
        if context:
            message += f' (near {context!r})'
        super().__init__(message, source_pos, source_line)


class LHTMLIncludeLoopError(LHTMLError):
    """Too many include iterations — likely a circular include."""

    def __init__(self, max_iterations: int = 20, chain: list[str] | None = None):
        self.chain = chain or []
        message = f'Circular or too deep include (max depth {max_iterations})'
        if self.chain:
            message += ': ' + ' -> '.join(self.chain)
        super().__init__(message)


def pos_to_line(text: str, pos: int) -> int:
    """Convert a character position to a 1-based line number."""
    if pos < 0 or pos > len(text):
        return -1
    return text[:pos].count('\n') + 1
