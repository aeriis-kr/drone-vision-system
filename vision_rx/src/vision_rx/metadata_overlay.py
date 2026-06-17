"""Render Pi pose metadata onto decoded receiver frames."""

from __future__ import annotations

import importlib
from typing import Any

from vision_rx.metadata import PoseMetadataFrame

POSE_VISIBILITY_THRESHOLD = 0.2
BLAZEPOSE_EDGES = ((11, 13), (13, 15), (12, 14), (14, 16), (11, 12), (11, 23), (12, 24), (23, 24))

_GREEN = (0, 255, 0)
_CYAN = (255, 255, 0)
_AMBER = (0, 191, 255)
_WHITE = (255, 255, 255)


def render_metadata_overlay(
    frame: Any,
    metadata: PoseMetadataFrame | None,
    *,
    age_s: float | None,
    stale_after_s: float,
    waiting: bool = False,
    metadata_port: int = 5001,
) -> Any:
    if waiting:
        cv2 = _cv2()
        if cv2 is None:
            return frame
        frame = _writeable(frame)
        _draw_text(cv2, frame, f"Pi metadata: waiting on UDP {metadata_port}", (12, 64), _AMBER)
        return frame

    if metadata is None:
        return frame

    cv2 = _cv2()
    if cv2 is None:
        return frame

    frame = _writeable(frame)
    if age_s is not None and age_s > stale_after_s:
        _draw_text(cv2, frame, f"Pi metadata stale {age_s:.1f}s", (12, 64), _AMBER)
        return frame

    frame_height, frame_width = frame.shape[:2]
    _draw_detections(cv2, frame, metadata, frame_width, frame_height)
    _draw_poses(cv2, frame, metadata, frame_width, frame_height)
    _draw_hud(cv2, frame, metadata, 0.0 if age_s is None else age_s)
    return frame


def _cv2() -> Any | None:
    try:
        return importlib.import_module("cv2")
    except ImportError:
        return None


def _writeable(frame: Any) -> Any:
    if hasattr(frame, "flags") and not frame.flags.writeable:
        return frame.copy()
    return frame


def _draw_detections(cv2: Any, frame: Any, metadata: PoseMetadataFrame, frame_width: int, frame_height: int) -> None:
    source_width = metadata.width if metadata.width > 0 else frame_width
    source_height = metadata.height if metadata.height > 0 else frame_height
    scale_x = frame_width / source_width
    scale_y = frame_height / source_height
    for detection in metadata.detections:
        x1 = int(detection.bbox[0] * scale_x)
        y1 = int(detection.bbox[1] * scale_y)
        x2 = int(detection.bbox[2] * scale_x)
        y2 = int(detection.bbox[3] * scale_y)
        label = f"{detection.class_name} {detection.confidence:.2f}"
        cv2.rectangle(frame, (x1, y1), (x2, y2), _GREEN, 2)
        _draw_text(cv2, frame, label, (x1, max(0, y1 - 8)), _GREEN, scale=0.6)


def _draw_poses(cv2: Any, frame: Any, metadata: PoseMetadataFrame, frame_width: int, frame_height: int) -> None:
    for pose in metadata.poses:
        points: list[tuple[int, int] | None] = []
        for landmark in pose:
            if landmark.visibility < POSE_VISIBILITY_THRESHOLD:
                points.append(None)
                continue
            x = int(landmark.x * frame_width)
            y = int(landmark.y * frame_height)
            points.append((x, y))
            cv2.circle(frame, (x, y), 4, _CYAN, -1)

        for start, end in BLAZEPOSE_EDGES:
            if start >= len(points) or end >= len(points):
                continue
            start_point = points[start]
            end_point = points[end]
            if start_point is None or end_point is None:
                continue
            cv2.line(frame, start_point, end_point, _CYAN, 2)


def _draw_hud(cv2: Any, frame: Any, metadata: PoseMetadataFrame, age_s: float) -> None:
    lines = [
        f"Pi gesture raw={metadata.gesture.raw} stable={metadata.gesture.stable} conf={metadata.gesture.confidence:.2f}",
        f"reason={_truncate(metadata.gesture.reason, 96)}",
    ]
    if metadata.trigger is not None:
        lines.append(f"trigger direction={metadata.trigger.direction} source={metadata.trigger.source}")
    if metadata.control is not None:
        target = "n/a" if metadata.control.target_mode is None else metadata.control.target_mode
        lines.append(
            f"control executed={metadata.control.executed} reason={metadata.control.reason} target={target}"
        )
        altitude = (
            "unknown"
            if metadata.control.vehicle_altitude_m is None
            else f"{metadata.control.vehicle_altitude_m:.2f}m"
        )
        lines.append(
            f"vehicle mode={metadata.control.vehicle_mode} "
            f"armed={metadata.control.vehicle_armed} altitude={altitude}"
        )
    lines.append(f"metadata age={age_s:.2f}s frame={metadata.frame_id}")

    y = 64
    for line in lines:
        _draw_text(cv2, frame, line, (12, y), _WHITE)
        y += 28


def _draw_text(
    cv2: Any,
    frame: Any,
    text: str,
    origin: tuple[int, int],
    color: tuple[int, int, int],
    *,
    scale: float = 0.7,
) -> None:
    cv2.putText(
        frame,
        text,
        origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        2,
        cv2.LINE_AA,
    )


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"
