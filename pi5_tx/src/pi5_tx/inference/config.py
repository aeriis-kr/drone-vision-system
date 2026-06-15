"""Configuration for Pi-local camera-frame inference."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class PiInferenceConfig:
    """Runtime settings for Pi-local YOLO inference."""

    model: str = "yolo11n.pt"
    confidence: float = 0.25
    imgsz: int = 640
    device: str = "auto"
    enabled: bool = True
    max_frames: int | None = None

    @classmethod
    def from_env(cls) -> "PiInferenceConfig":
        """Build a config from DVS_* or Makefile-friendly environment variables."""

        return cls(
            model=os.getenv("DVS_MODEL") or os.getenv("MODEL") or "yolo11n.pt",
            confidence=float(os.getenv("DVS_CONF") or os.getenv("CONF") or "0.25"),
            imgsz=int(os.getenv("DVS_IMGSZ") or os.getenv("IMGSZ") or "640"),
            device=os.getenv("DVS_DEVICE") or os.getenv("DEVICE") or "auto",
            enabled=not _truthy(os.getenv("DVS_NO_INFERENCE") or os.getenv("NO_INFERENCE")),
            max_frames=_optional_int(
                os.getenv("DVS_INFERENCE_MAX_FRAMES") or os.getenv("INFERENCE_MAX_FRAMES")
            ),
        )


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "y", "on"}


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
