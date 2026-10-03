"""Lark-based parser for the LHTML :: tag element subsystem.

The grammar is defined in tag_element.lark and handles the syntax
after :: in constructs like:

    tag::(.class #id)[style]{attrs}text::
    div::[color:red;]
    link::url[link text]
    ::(.class)[style]
    ::nl
    ::   (closing tag)

Supports nested brackets: [outer[inner]still_outer]
"""

import os
import re

from lark import Lark, Transformer, UnexpectedInput

from .errors import LHTMLParseError


# ---------------------------------------------------------------------------
# Load grammar from .lark file
# ---------------------------------------------------------------------------

_GRAMMAR_PATH = os.path.join(os.path.dirname(__file__), 'tag_element.lark')

with open(_GRAMMAR_PATH) as _f:
    _GRAMMAR_TEXT = _f.read()

_parser = Lark(_GRAMMAR_TEXT, parser='earley', ambiguity='resolve')

_TAG_NAME_BEFORE = re.compile(r'[A-Za-z][A-Za-z0-9_-]*\Z')
_MAX_TAG_NAME = 64


# ---------------------------------------------------------------------------
# Transformer: parse tree -> element dict
# ---------------------------------------------------------------------------

class _TagElementTransformer(Transformer):
    """Transforms Lark parse tree into element dict."""

    # Content is transformed bottom-up: nested groups are already strings
    # and get their delimiters back here.

    def paren_content(self, items):
        return ''.join(str(item) for item in items)

    square_content = paren_content
    curly_content = paren_content

    def paren_nested(self, items):
        return '(' + (items[0] if items else '') + ')'

    def square_nested(self, items):
        return '[' + (items[0] if items else '') + ']'

    def curly_nested(self, items):
        return '{' + (items[0] if items else '') + '}'

    def paren_group(self, items):
        return ('()', items[0] if items else '')

    def square_group(self, items):
        return ('[]', items[0] if items else '')

    def curly_group(self, items):
        return ('{}', items[0] if items else '')

    def bare_text(self, items):
        return ('text', str(items[0]))

    def bracket_and_text(self, items):
        return items[0]

    def start(self, items):
        return list(items)


_transformer = _TagElementTransformer()


# ---------------------------------------------------------------------------
# Forward scanner (bracket-aware)
# ---------------------------------------------------------------------------

def _scan_forward_bracket_aware(text, start):
    """Scan forward from start, respecting bracket nesting.

    Stops at whitespace, '<' (HTML produced by previous passes, such as
    </strong>) or a protected-zone placeholder (e.g. an HTML tag) outside
    brackets, or if text appears after a bracket group that was preceded
    by text. Protected URL placeholders (kind U) are part of the text.
    """
    idx = start
    length = len(text)
    bracket_pairs = {'(': ')', '[': ']', '{': '}'}
    seen_text = False
    seen_bracket_after_text = False

    while idx < length:
        ch = text[idx]
        if ch == '\x00' and text[idx + 1:idx + 2] == 'U':
            end = text.find('\x00', idx + 1)
            if end > idx:
                seen_text = True
                idx = end + 1
                continue
        if ch.isspace() or ch == '\x00' or ch == '<':
            break
        if ch in bracket_pairs:
            close = bracket_pairs[ch]
            depth = 1
            bracket_start = idx
            idx += 1
            while idx < length and depth > 0:
                if text[idx] == ch:
                    depth += 1
                elif text[idx] == close:
                    depth -= 1
                idx += 1
            if depth > 0:
                raise LHTMLParseError(
                    f'Unclosed bracket {ch!r} (expected {close!r})',
                    source_pos=bracket_start,
                )
            if seen_text:
                seen_bracket_after_text = True
            continue
        if seen_bracket_after_text:
            break
        seen_text = True
        idx += 1

    return text[start:idx]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_tag_after_colons(text_after_colons):
    """Parse the text that appears after :: in an LHTML tag element.

    Returns dict with keys '[]', '()', '{}', 'text'.
    """
    result = {'[]': '', '{}': '', '()': '', 'text': ''}
    if not text_after_colons:
        return result

    try:
        tree = _parser.parse(text_after_colons)
        items = _transformer.transform(tree)
    except (UnexpectedInput, RecursionError):
        result['text'] = text_after_colons
        return result

    text_parts = []
    text_finished = False

    for kind, content in items:
        if kind == 'text':
            if not text_finished:
                text_parts.append(content)
        else:
            if text_parts:
                text_finished = True
            if result[kind]:
                result[kind] += ' '
            result[kind] += content

    result['text'] = ''.join(text_parts)
    return result


def extract_bracket_elements_lark(text, index_start):
    """Extract bracket elements from an LHTML :: tag expression.

    Args:
        text: Full document text.
        index_start: Position right after :: (first char to parse).

    Returns:
        Dict with keys: '[]', '()', '{}', 'text', 'tag',
        'index_start', 'index_end'
    """
    elements = {
        '[]': '', '{}': '', '()': '', 'text': '',
        'tag': '', 'index_start': index_start, 'index_end': index_start,
    }

    # Backward scan for tag name (letter, then letters/digits/_/-)
    if index_start >= 2:
        name_end = index_start - 2
        m = _TAG_NAME_BEFORE.search(text, max(0, name_end - _MAX_TAG_NAME), name_end)
        tag_start = m.start() if m else name_end
        elements['tag'] = text[tag_start:name_end]
        elements['index_start'] = tag_start

    # Forward scan: bracket-aware extraction
    if index_start < len(text):
        after_colons = _scan_forward_bracket_aware(text, index_start)
        elements['index_end'] = index_start + len(after_colons)

        if after_colons:
            parsed = parse_tag_after_colons(after_colons)
            elements.update({k: parsed[k] for k in ('[]', '()', '{}', 'text')})

    return elements
