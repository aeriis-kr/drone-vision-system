"""Generic Linux platform backend."""

from __future__ import annotations


class LinuxBackend:
    name = "linux"
    default_device = "auto"
    default_display = "opencv"
    notes = "CUDA is selected when available; otherwise CPU fallback."
