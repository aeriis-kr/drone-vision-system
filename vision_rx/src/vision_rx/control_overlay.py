"""Draw receiver-side gesture/control status onto decoded frames."""

from __future__ import annotations

import importlib
from typing import Any

_WHITE = (255, 255, 255)
_AMBER = (0, 191, 255)


def render_control_overlay(
    frame: Any,
    *,
    raw_gesture: str,
    stable_gesture: str,
    confidence: float,
    reason: str,
    control: Any | None,
    control_host: str,
    control_port: int,
) -> Any:
    cv2 = _cv2()
    if cv2 is None:
        return frame
    if hasattr(frame, "flags") and not frame.flags.writeable:
        frame = frame.copy()

    lines = [
        f"RX gesture raw={raw_gesture} stable={stable_gesture} conf={confidence:.2f}",
        f"reason={_truncate(reason, 96)}",
        f"control tcp={control_host}:{control_port}",
    ]
    if control is None:
        lines.append("control waiting for stable UP trigger")
    else:
        target = "n/a" if control.target_mode is None else control.target_mode
        lines.append(f"control executed={control.executed} reason={control.reason} target={target}")
        altitude = "unknown" if control.vehicle_altitude_m is None else f"{control.vehicle_altitude_m:.2f}m"
        lines.append(
            f"vehicle mode={control.vehicle_mode} armed={control.vehicle_armed} altitude={altitude}"
        )

    y = 64
    for line in lines:
        _draw_text(cv2, frame, line, (12, y), _WHITE if control is not None else _AMBER)
        y += 28
    return frame


def _cv2() -> Any | None:
    try:
        return importlib.import_module("cv2")
    except ImportError:
        return None


def _draw_text(
    cv2: Any,
    frame: Any,
    text: str,
    origin: tuple[int, int],
    color: tuple[int, int, int],
    *,
    scale: float = 0.7,
) -> None:
    cv2.putText(frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"
