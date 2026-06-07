"""macOS platform backend."""

from __future__ import annotations


class MacOSBackend:
    name = "macos"
    default_device = "mps"
    default_display = "opencv"
    notes = "Apple Silicon uses Torch MPS when available; Intel Macs fall back to CPU."
