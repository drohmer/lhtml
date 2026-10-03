"""Backward-compatible store/restore functions (signatures of LHTML 2.2).

remove_element_to_index replaces each match of `regex` by `name::[index]`
and stores the matched text; insert_element_from_index restores them.
The pipeline itself uses patterns.store_to_index / restore_from_index.
"""

import re


def remove_element_to_index(text, regex, name, store):
    """Replace matches of `regex` by `name::[index]`, storing the matched text."""
    pattern = re.compile(regex, re.DOTALL | re.MULTILINE) if isinstance(regex, str) else regex

    def _store(m):
        store.append(m.group(0))
        return f'{name}::[{len(store) - 1}]'
    return pattern.sub(_store, text)


def insert_element_from_index(text, regex, store):
    """Replace matches of `regex` (whose group 1 is an index) by the stored text."""
    pattern = re.compile(regex) if isinstance(regex, str) else regex

    def _restore(m):
        idx = m.group(1)
        if not idx.isdigit() or int(idx) >= len(store):
            return m.group(0)
        return store[int(idx)]
    return pattern.sub(_restore, text)
