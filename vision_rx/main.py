"""Compatibility wrapper for `uv run python main.py`."""

from __future__ import annotations

from pathlib import Path
import runpy
import sys

PACKAGE_SRC = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(PACKAGE_SRC))


if __name__ == "__main__":
    module_globals = runpy.run_path(str(PACKAGE_SRC / "vision_rx" / "main.py"))
    raise SystemExit(module_globals["main"]())
