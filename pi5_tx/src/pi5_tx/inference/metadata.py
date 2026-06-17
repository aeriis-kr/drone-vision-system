"""UDP pose metadata emitted beside the Pi video stream."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import socket

from pi5_tx.automation.events import TriggerEvent
from pi5_tx.automation.gesture_control import AltitudeControlResult
from pi5_tx.inference.detections import Detection
from pi5_tx.inference.gesture_types import Gesture, GestureDecision, Landmark

METADATA_SCHEMA = "dvs.pose_metadata.v1"
DEFAULT_METADATA_PORT = 5001
_TRUTHY = {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True, slots=True)
class MetadataSenderConfig:
    host: str
    port: int = DEFAULT_METADATA_PORT
    enabled: bool = True

    @classmethod
    def from_env(cls, default_host: str) -> "MetadataSenderConfig":
        host = os.getenv("DVS_METADATA_HOST") or os.getenv("METADATA_HOST") or default_host
        port = int(os.getenv("DVS_METADATA_PORT") or os.getenv("METADATA_PORT") or DEFAULT_METADATA_PORT)
        disabled = _truthy(os.getenv("DVS_NO_METADATA") or os.getenv("NO_METADATA"))
        return cls(host=host, port=port, enabled=not disabled)


@dataclass(frozen=True, slots=True)
class MetadataTriggerState:
    direction: str
    confidence: float
    source: str
    reason: str
    created_at_s: float


@dataclass(frozen=True, slots=True)
class MetadataControlState:
    executed: bool
    reason: str
    target_mode: str | None
    vehicle_mode: str | None
    vehicle_armed: bool | None
    vehicle_altitude_m: float | None


@dataclass(frozen=True, slots=True)
class MetadataFrame:
    frame_id: int
    created_at_s: float
    width: int
    height: int
    detections: tuple[Detection, ...]
    poses: tuple[tuple[Landmark, ...], ...]
    decision: GestureDecision
    stable: Gesture
    trigger: MetadataTriggerState | None = None
    control: MetadataControlState | None = None


def control_state_from_result(result: AltitudeControlResult | None) -> MetadataControlState | None:
    if result is None:
        return None
    return MetadataControlState(
        executed=result.executed,
        reason=result.reason,
        target_mode=result.target_mode,
        vehicle_mode=result.vehicle_mode,
        vehicle_armed=result.vehicle_armed,
        vehicle_altitude_m=result.vehicle_altitude_m,
    )


def trigger_state_from_event(event: TriggerEvent | None) -> MetadataTriggerState | None:
    if event is None:
        return None
    return MetadataTriggerState(
        direction=event.direction,
        confidence=event.confidence,
        source=event.source,
        reason=event.reason,
        created_at_s=event.created_at_s,
    )


def metadata_payload(frame: MetadataFrame) -> dict[str, object]:
    return {
        "schema": METADATA_SCHEMA,
        "frame_id": frame.frame_id,
        "created_at_s": frame.created_at_s,
        "width": frame.width,
        "height": frame.height,
        "detections": [
            {
                "class_id": detection.class_id,
                "class_name": detection.class_name,
                "confidence": round(detection.confidence, 4),
                "bbox": [
                    round(detection.x1, 1),
                    round(detection.y1, 1),
                    round(detection.x2, 1),
                    round(detection.y2, 1),
                ],
            }
            for detection in frame.detections
        ],
        "poses": [
            [
                [
                    round(landmark.x, 4),
                    round(landmark.y, 4),
                    round(landmark.visibility, 4),
                    round(landmark.z, 4),
                ]
                for landmark in pose
            ]
            for pose in frame.poses
        ],
        "gesture": {
            "raw": frame.decision.gesture.value,
            "stable": frame.stable.value,
            "confidence": round(frame.decision.confidence, 4),
            "reason": frame.decision.reason,
        },
        "trigger": _trigger_payload(frame.trigger),
        "control": _control_payload(frame.control),
    }


def encode_metadata(frame: MetadataFrame) -> bytes:
    return json.dumps(metadata_payload(frame), separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class MetadataUDPSender:
    def __init__(self, config: MetadataSenderConfig) -> None:
        self._config = config
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._send_error_reported = False

    def send(self, frame: MetadataFrame) -> None:
        try:
            self._socket.sendto(encode_metadata(frame), (self._config.host, self._config.port))
        except OSError as exc:
            if not self._send_error_reported:
                print(f"[pi5-metadata] send error: {exc}")
                self._send_error_reported = True

    def close(self) -> None:
        self._socket.close()


def _trigger_payload(trigger: MetadataTriggerState | None) -> dict[str, object] | None:
    if trigger is None:
        return None
    return {
        "direction": trigger.direction,
        "confidence": round(trigger.confidence, 4),
        "source": trigger.source,
        "reason": trigger.reason,
        "created_at_s": trigger.created_at_s,
    }


def _control_payload(control: MetadataControlState | None) -> dict[str, object] | None:
    if control is None:
        return None
    return {
        "executed": control.executed,
        "reason": control.reason,
        "target_mode": control.target_mode,
        "vehicle_mode": control.vehicle_mode,
        "vehicle_armed": control.vehicle_armed,
        "vehicle_altitude_m": control.vehicle_altitude_m,
    }


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in _TRUTHY
