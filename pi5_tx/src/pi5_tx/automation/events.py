"""Event models for future Pi-side automation triggers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AltitudeDirection = Literal["UP", "DOWN"]


@dataclass(frozen=True, slots=True)
class TriggerEvent:
    """A candidate automation trigger emitted by perception wiring."""

    direction: AltitudeDirection
    confidence: float
    source: str
    created_at_s: float
    reason: str
