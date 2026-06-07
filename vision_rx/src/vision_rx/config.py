"""Configuration for the cross-platform receiver pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ReceiverConfig:
    bind_host: str = "0.0.0.0"
    port: int = 5000
    width: int = 1280
    height: int = 720
    fps: int = 30
    stream_format: str = "mpegts"
    ffmpeg_path: str = "ffmpeg"
    model: str = "yolo11n.pt"
    confidence: float = 0.25
    imgsz: int = 640
    device: str = "auto"
    display: str = "opencv"
    inference: bool = True
    show_fps: bool = True

    @property
    def frame_bytes(self) -> int:
        return self.width * self.height * 3

    @classmethod
    def from_env(cls) -> "ReceiverConfig":
        return cls(
            bind_host=os.getenv("DVS_BIND_HOST") or os.getenv("BIND_HOST") or "0.0.0.0",
            port=int(os.getenv("DVS_STREAM_PORT") or os.getenv("STREAM_PORT") or "5000"),
            width=int(os.getenv("DVS_WIDTH") or os.getenv("WIDTH") or "1280"),
            height=int(os.getenv("DVS_HEIGHT") or os.getenv("HEIGHT") or "720"),
            fps=int(os.getenv("DVS_FPS") or os.getenv("FPS") or "30"),
            stream_format=os.getenv("DVS_STREAM_FORMAT")
            or os.getenv("STREAM_FORMAT")
            or "mpegts",
            ffmpeg_path=os.getenv("DVS_FFMPEG") or os.getenv("FFMPEG") or "ffmpeg",
            model=os.getenv("DVS_MODEL") or os.getenv("MODEL") or "yolo11n.pt",
            confidence=float(os.getenv("DVS_CONF") or os.getenv("CONF") or "0.25"),
            imgsz=int(os.getenv("DVS_IMGSZ") or os.getenv("IMGSZ") or "640"),
            device=os.getenv("DVS_DEVICE") or os.getenv("DEVICE") or "auto",
            display=os.getenv("DVS_DISPLAY") or os.getenv("RX_DISPLAY") or "opencv",
            inference=not _truthy(os.getenv("DVS_NO_INFERENCE") or os.getenv("NO_INFERENCE")),
            show_fps=not _truthy(os.getenv("DVS_NO_FPS") or os.getenv("NO_FPS")),
        )


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "y", "on"}
