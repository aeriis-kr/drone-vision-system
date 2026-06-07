"""Configuration models for the Raspberry Pi transmitter."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class StreamConfig:
    """Runtime settings for H264 camera streaming."""

    host: str
    port: int = 5000
    width: int = 1280
    height: int = 720
    fps: int = 30
    bitrate: int = 3_000_000
    stream_format: str = "mpegts"
    camera_command: str | None = None
    preview: bool = False
    inline_headers: bool = True
    dry_run: bool = False

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    @classmethod
    def from_env(cls) -> "StreamConfig":
        """Build a config from DVS_* or Makefile-friendly environment variables."""

        return cls(
            host=os.getenv("DVS_TX_HOST") or os.getenv("STREAM_HOST") or "127.0.0.1",
            port=int(os.getenv("DVS_STREAM_PORT") or os.getenv("STREAM_PORT") or "5000"),
            width=int(os.getenv("DVS_WIDTH") or os.getenv("WIDTH") or "1280"),
            height=int(os.getenv("DVS_HEIGHT") or os.getenv("HEIGHT") or "720"),
            fps=int(os.getenv("DVS_FPS") or os.getenv("FPS") or "30"),
            bitrate=int(os.getenv("DVS_BITRATE") or os.getenv("BITRATE") or "3000000"),
            stream_format=os.getenv("DVS_STREAM_FORMAT")
            or os.getenv("STREAM_FORMAT")
            or "mpegts",
            camera_command=os.getenv("DVS_CAMERA_COMMAND") or os.getenv("CAMERA_COMMAND"),
            preview=_truthy(os.getenv("DVS_PREVIEW") or os.getenv("PREVIEW")),
            dry_run=_truthy(os.getenv("DVS_DRY_RUN") or os.getenv("DRY_RUN")),
        )


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "y", "on"}
