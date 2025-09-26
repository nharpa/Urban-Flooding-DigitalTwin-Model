"""CLI package for Urban Flooding Digital Twin.

Execute via:
  python -m urban_flooding.cli <command> [options]

Or (after adding a console script in packaging metadata) simply:
  flooding-twin <command>

Commands implemented in `main.py` using the standard library `argparse`.
"""

from .main import main  # re-export for python -m urban_flooding.cli

__all__ = ["main"]
