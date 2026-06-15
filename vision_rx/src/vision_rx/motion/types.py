"""Motion-event data types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Gesture(StrEnum):
    """High-level vertical gesture command."""

    UNKNOWN = "UNKNOWN"
    STOP = "STOP"
    UP = "UP"
    DOWN = "DOWN"


@dataclass(frozen=True, slots=True)
class GestureDecision:
    """Classifier output for one pose frame."""

    gesture: Gesture
    confidence: float
    reason: str


@dataclass(frozen=True, slots=True)
class Landmark:
    """Normalized pose landmark.

    Coordinates follow image convention: x grows right, y grows down. Visibility
    is expected to be in [0, 1]. z is kept for pose backends that provide it,
    but the current vertical gesture classifier uses only x/y/visibility.
    """

    x: float
    y: float
    visibility: float = 1.0
    z: float = 0.0
