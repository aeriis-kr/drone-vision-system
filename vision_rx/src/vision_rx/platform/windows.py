"""Windows platform backend."""

from __future__ import annotations


class WindowsBackend:
    name = "windows"
    default_device = "auto"
    default_display = "opencv"
    notes = "CUDA is used when Torch reports it; otherwise CPU fallback."
