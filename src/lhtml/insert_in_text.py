"""Backward-compatible aliases for store/restore functions.

The actual implementations are in patterns.py.
"""

from .patterns import store_to_index as remove_element_to_index
from .patterns import restore_from_index as insert_element_from_index
