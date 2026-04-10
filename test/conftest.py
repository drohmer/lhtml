"""Pytest configuration for LHTML tests."""

import sys
import os

# Add src/ to path so lhtml can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
