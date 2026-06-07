"""Platform abstraction layer."""

from __future__ import annotations

import importlib
from typing import Any


def detect_backend() -> Any:
    return importlib.import_module("vision_rx.platform.detect").detect_backend()


__all__ = ["detect_backend"]
