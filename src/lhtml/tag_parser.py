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

from lark import Lark, Transformer, UnexpectedInput

from .errors import LHTMLParseError


# ---------------------------------------------------------------------------
# Load grammar from .lark file
# ---------------------------------------------------------------------------

_GRAMMAR_PATH = os.path.join(os.path.dirname(__file__), 'tag_element.lark')

with open(_GRAMMAR_PATH) as _f:
    _GRAMMAR_TEXT = _f.read()

_parser = Lark(_GRAMMAR_TEXT, parser='earley', ambiguity='resolve')


# ---------------------------------------------------------------------------
# Transformer: parse tree -> element dict
# ---------------------------------------------------------------------------

class _TagElementTransformer(Transformer):
    """Transforms Lark parse tree into element dict."""

    def _flatten_content(self, items):
        """Recursively flatten nested bracket content to a string."""
        parts = []
        for item in items:
            if hasattr(item, 'data'):
                name = item.data
                inner = self._flatten_content(item.children)
                if 'paren' in name:
                    parts.append(f'({inner})')
                elif 'square' in name:
                    parts.append(f'[{inner}]')
                elif 'curly' in name:
                    parts.append('{' + inner + '}')
            else:
                parts.append(str(item))
        return ''.join(parts)

    def paren_content(self, items):
        return self._flatten_content(items)

    def square_content(self, items):
        return self._flatten_content(items)

    def curly_content(self, items):
        return self._flatten_content(items)

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

    Stops at space/newline outside brackets, or if text appears after
    a bracket group that was preceded by text.
    """
    idx = start
    length = len(text)
    bracket_pairs = {'(': ')', '[': ']', '{': '}'}
    seen_text = False
    seen_bracket_after_text = False

    while idx < length:
        ch = text[idx]
        if ch == ' ' or ch == '\n':
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
    except UnexpectedInput:
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

    # Backward scan for tag name
    if index_start >= 2:
        idx = index_start - 2
        while idx > 0 and text[idx] != '\n' and text[idx] != ' ' and (text[idx].isalpha() or text[idx] == ':'):
            idx -= 1
        if idx == 0 and (text[idx].isalpha() or text[idx] == ':'):
            tag_start = 0
        elif text[idx] == '\n' or text[idx] == ' ' or not (text[idx].isalpha() or text[idx] == ':'):
            tag_start = idx + 1
        else:
            tag_start = idx
        elements['tag'] = text[tag_start:index_start - 2]
        elements['index_start'] = tag_start

    # Forward scan: bracket-aware extraction
    if index_start < len(text):
        after_colons = _scan_forward_bracket_aware(text, index_start)
        elements['index_end'] = index_start + len(after_colons)

        if after_colons:
            parsed = parse_tag_after_colons(after_colons)
            elements.update({k: parsed[k] for k in ('[]', '()', '{}', 'text')})

    return elements
