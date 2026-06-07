"""Base platform backend data model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformBackend:
    name: str
    default_device: str = "auto"
    default_display: str = "opencv"
    notes: str = ""
