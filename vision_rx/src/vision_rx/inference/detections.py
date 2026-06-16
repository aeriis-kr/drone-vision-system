"""Structured inference results shared by display and motion logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vision_rx.motion.types import Landmark


@dataclass(frozen=True)
class Detection:
    """Single object detection in image coordinates."""

    class_id: int
    class_name: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) * 0.5

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) * 0.5



@dataclass(frozen=True)
class InferenceResult:
    """Inference output for one frame before optional rendering."""

    frame: Any
    detections: tuple[Detection, ...]
    poses: tuple[tuple[Landmark, ...], ...] = ()
