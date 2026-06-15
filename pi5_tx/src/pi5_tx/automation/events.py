"""Event models for future Pi-side automation triggers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AltitudeDirection = Literal["UP", "DOWN"]


@dataclass(frozen=True, slots=True)
class TriggerEvent:
    """A candidate altitude-change trigger emitted by future perception wiring."""

    direction: AltitudeDirection
    confidence: float
    source: str
    created_at_s: float
    reason: str
