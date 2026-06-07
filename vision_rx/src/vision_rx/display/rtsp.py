"""RTSP restream display backend placeholder.

The architecture reserves this module for Jetson/headless deployments.  The
current MVP keeps the API explicit so callers fail fast if they request it before
an RTSP server implementation is added.
"""

from __future__ import annotations

from typing import Any


class RTSPDisplay:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError("RTSP restream backend is reserved for a future extension")

    def show(self, _frame: Any) -> bool:
        return True

    def close(self) -> None:
        return None
