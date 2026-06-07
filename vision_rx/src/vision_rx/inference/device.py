"""Hardware accelerator selection for YOLO inference."""

from __future__ import annotations

import importlib


def select_device(preferred: str = "auto") -> str:
    """Return cuda, mps, or cpu unless the user explicitly selected a device."""

    normalized = preferred.lower()
    if normalized != "auto":
        return preferred

    try:
        torch = importlib.import_module("torch")
    except ImportError:
        return "cpu"

    cuda = getattr(torch, "cuda", None)
    if cuda is not None and cuda.is_available():
        return "cuda"

    backends = getattr(torch, "backends", None)
    mps = getattr(backends, "mps", None) if backends is not None else None
    if mps is not None and mps.is_available():
        return "mps"

    return "cpu"
