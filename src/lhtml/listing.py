"""List processing for LHTML.

Converts * item / ** subitem syntax to nested <ul><li> HTML.
"""

import io
import re

_LIST_ITEM = re.compile(r'^(\*+) (.*)')


def _analyse_line(line):
    """Extract nesting level and content from a line."""
    m = _LIST_ITEM.search(line)
    if m:
        return len(m.group(1)), m.group(2) + '\n'
    return 0, line


def process_listing(text):
    """Convert * / ** / *** list items to nested <ul><li> HTML."""
    lines = []
    buf = io.StringIO(text)
    for line in buf:
        lines.append(_analyse_line(line))

    parts = []
    level = 0

    for k, (line_level, content) in enumerate(lines):
        # Open deeper levels
        while level < line_level:
            level += 1
            if level > 1:
                parts.append('<li>\n')
            parts.append('<ul>\n')

        if level > 0:
            parts.append('<li>\n')

        parts.append(content)

        if level > 0:
            parts.append('</li>\n')

        # Close shallower levels (peek at next line)
        next_level = lines[k + 1][0] if k < len(lines) - 1 else 0
        while level > next_level:
            level -= 1
            parts.append('</ul>\n')
            if level >= 1:
                parts.append('</li>\n')

    return ''.join(parts)
