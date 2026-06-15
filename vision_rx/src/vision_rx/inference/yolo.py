"""YOLO inference wrapper."""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib
from typing import Any

from vision_rx.inference.detections import Detection, InferenceResult


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
        return InferenceResult(
            frame=frame,
            detections=self._detections_from_result(results[0]),
        )

    def render(self, frame: Any, detections: tuple[Detection, ...]) -> Any:
        if not detections:
            return frame

        try:
            cv2 = importlib.import_module("cv2")
        except ImportError:
            return frame

        if hasattr(frame, "flags") and not frame.flags.writeable:
            frame = frame.copy()

        for detection in detections:
            x1, y1, x2, y2 = (
                int(detection.x1),
                int(detection.y1),
                int(detection.x2),
                int(detection.y2),
            )
            label = f"{detection.class_name} {detection.confidence:.2f}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(
                frame,
                label,
                (x1, max(0, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
        return frame

    def process(self, frame: Any) -> Any:
        result = self.detect(frame)
        return self.render(result.frame, result.detections)

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
                "ultralytics is not installed. Run `make setup-rx`, or start with NO_INFERENCE=1."
            ) from exc

        yolo_class = getattr(ultralytics, "YOLO")
        print(f"[vision-rx] loading YOLO model={self.model_name} device={self.device}")
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
