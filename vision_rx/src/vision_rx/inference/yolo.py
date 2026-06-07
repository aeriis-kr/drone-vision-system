"""YOLO inference wrapper."""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib
from typing import Any


class InferenceError(RuntimeError):
    """Raised when YOLO dependencies or runtime fail."""


@dataclass
class YoloDetector:
    model_name: str = "yolo11n.pt"
    confidence: float = 0.25
    imgsz: int = 640
    device: str = "cpu"
    enabled: bool = True
    _model: Any = field(default=None, init=False, repr=False)

    def process(self, frame: Any) -> Any:
        if not self.enabled:
            return frame

        model = self._load_model()
        results = model.predict(
            frame,
            imgsz=self.imgsz,
            conf=self.confidence,
            device=self.device,
            verbose=False,
        )
        if not results:
            return frame
        return results[0].plot()

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            ultralytics = importlib.import_module("ultralytics")
        except ImportError as exc:
            raise InferenceError(
                "ultralytics is not installed. Run `make setup-rx`, or start with NO_INFERENCE=1."
            ) from exc

        yolo_class = getattr(ultralytics, "YOLO")
        print(f"[vision-rx] loading YOLO model={self.model_name} device={self.device}")
        self._model = yolo_class(self.model_name)
        return self._model
