"""Initialize schema migrations only; this project intentionally ships no fabricated seed measurements."""
from __future__ import annotations
import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("migrate.py")), run_name="__main__")
