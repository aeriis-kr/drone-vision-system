"""OpenCV display backend."""

from __future__ import annotations

import importlib
from typing import Any


class OpenCVDisplay:
    def __init__(self, window_name: str = "Drone Vision System") -> None:
        self.window_name = window_name
        try:
            self._cv2 = importlib.import_module("cv2")
        except ImportError as exc:
            raise RuntimeError("opencv-python is not installed. Run `make setup-rx`.") from exc

    def show(self, frame: Any) -> bool:
        """Show a frame.  Return False when the user requests shutdown."""

        self._cv2.imshow(self.window_name, frame)
        key = self._cv2.waitKey(1) & 0xFF
        return key not in {ord("q"), 27}

    def close(self) -> None:
        self._cv2.destroyAllWindows()
