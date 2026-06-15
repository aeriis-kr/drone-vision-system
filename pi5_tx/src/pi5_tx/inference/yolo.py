"""Pi-local YOLO inference wrapper."""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib
from typing import Any

from pi5_tx.inference.detections import Detection, InferenceResult
from pi5_tx.inference.pose import landmarks_from_yolo_pose_result


class InferenceError(RuntimeError):
    """Raised when Pi-local YOLO dependencies or runtime fail."""


@dataclass
class YoloDetector:
    model_name: str = "yolo11n.pt"
    confidence: float = 0.25
    imgsz: int = 640
    device: str = "cpu"
    enabled: bool = True
    _model: Any = field(default=None, init=False, repr=False)

    def detect(self, frame: Any) -> InferenceResult:
        if not self.enabled:
            return InferenceResult(frame=frame, detections=())

        model = self._load_model()
        results = model.predict(
            frame,
            imgsz=self.imgsz,
            conf=self.confidence,
            device=self.device,
            verbose=False,
        )
        if not results:
            return InferenceResult(frame=frame, detections=())
        result = results[0]
        return InferenceResult(
            frame=frame,
            detections=self._detections_from_result(result),
            poses=landmarks_from_yolo_pose_result(result),
        )

    def _detections_from_result(self, result: Any) -> tuple[Detection, ...]:
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return ()

        names = getattr(result, "names", None) or getattr(self._model, "names", {})
        detections: list[Detection] = []
        for box in boxes:
            xyxy = _tolist(box.xyxy[0])
            cls_values = _tolist(box.cls)
            conf_values = _tolist(box.conf)
            if len(xyxy) < 4 or not cls_values or not conf_values:
                continue
            class_id = int(cls_values[0])
            detections.append(
                Detection(
                    class_id=class_id,
                    class_name=str(_class_name(names, class_id)),
                    confidence=float(conf_values[0]),
                    x1=float(xyxy[0]),
                    y1=float(xyxy[1]),
                    x2=float(xyxy[2]),
                    y2=float(xyxy[3]),
                )
            )
        return tuple(detections)

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            ultralytics = importlib.import_module("ultralytics")
        except ImportError as exc:
            raise InferenceError(
                "ultralytics is not installed. Run `make setup-pi`, or start with NO_INFERENCE=1."
            ) from exc

        yolo_class = getattr(ultralytics, "YOLO")
        print(f"[pi5-inference] loading YOLO model={self.model_name} device={self.device}")
        self._model = yolo_class(self.model_name)
        return self._model


def _tolist(value: Any) -> list[Any]:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        result = value.tolist()
        return result if isinstance(result, list) else [result]
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _class_name(names: Any, class_id: int) -> Any:
    if isinstance(names, dict):
        return names.get(class_id, class_id)
    if isinstance(names, (list, tuple)) and 0 <= class_id < len(names):
        return names[class_id]
    return class_id
