"""LHTML element extraction from :: tag syntax.

Delegates to the Lark-based parser in tag_parser.py for robust
bracket parsing with proper nesting support.
"""

from .tag_parser import extract_bracket_elements_lark


def extract_bracket_elements(text, index_start):
    """Extract bracket elements from an LHTML :: tag expression.

    Args:
        text: Full document text.
        index_start: Position right after :: (first char to parse).

    Returns:
        Dict with keys: '[]', '()', '{}', 'text', 'tag',
        'index_start', 'index_end'
    """
    return extract_bracket_elements_lark(text, index_start)
