"""WebRTC display backend placeholder."""

from __future__ import annotations

from typing import Any


class WebRTCDisplay:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError("WebRTC display backend is reserved for a future extension")

    def show(self, _frame: Any) -> bool:
        return True

    def close(self) -> None:
        return None
