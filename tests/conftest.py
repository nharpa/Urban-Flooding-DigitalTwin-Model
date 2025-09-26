"""Pytest configuration ensuring the `src` directory is on sys.path.

Allows `import urban_flooding...` without installing the package.
"""
import sys
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)
