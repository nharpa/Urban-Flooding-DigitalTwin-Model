"""Standalone database initialization helper.

Equivalent to running:
    python -m urban_flooding.cli init-db

Useful for container ENTRYPOINT or quick local bootstrap without recalling
CLI syntax. Idempotent: safe to run multiple times.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the src/ directory is on sys.path when running the script directly
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from urban_flooding.persistence.database import FloodingDatabase  # noqa: E402


def main() -> int:
    try:
        db = FloodingDatabase()
        print("MongoDB initialization successful. Collections present:")
        for name in db.db.list_collection_names():
            print(f" - {name}")
        db.close()
        return 0
    except Exception as exc:  # pragma: no cover
        print(f"Initialization failed: {exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
