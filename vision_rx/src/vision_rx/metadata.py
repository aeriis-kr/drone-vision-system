"""Receiver-side parser for Pi pose metadata packets."""

from __future__ import annotations

from dataclasses import dataclass
import json
import socket
import threading
import time

METADATA_SCHEMA = "dvs.pose_metadata.v1"
DEFAULT_METADATA_PORT = 5001
_MAX_DATAGRAM_BYTES = 65535
_SOCKET_TIMEOUT_S = 0.2


@dataclass(frozen=True, slots=True)
class MetadataDetection:
    class_id: int
    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class MetadataLandmark:
    x: float
    y: float
    visibility: float
    z: float


@dataclass(frozen=True, slots=True)
class MetadataGesture:
    raw: str
    stable: str
    confidence: float
    reason: str


@dataclass(frozen=True, slots=True)
class MetadataTrigger:
    direction: str
    confidence: float
    source: str
    reason: str
    created_at_s: float


@dataclass(frozen=True, slots=True)
class MetadataControl:
    executed: bool
    reason: str
    target_altitude_m: float | None
    vehicle_mode: str | None
    vehicle_armed: bool | None
    vehicle_altitude_m: float | None


@dataclass(frozen=True, slots=True)
class PoseMetadataFrame:
    frame_id: int
    created_at_s: float
    width: int
    height: int
    detections: tuple[MetadataDetection, ...]
    poses: tuple[tuple[MetadataLandmark, ...], ...]
    gesture: MetadataGesture
    trigger: MetadataTrigger | None
    control: MetadataControl | None


@dataclass(frozen=True, slots=True)
class ReceivedMetadata:
    frame: PoseMetadataFrame
    received_at_s: float


def decode_metadata(data: bytes) -> PoseMetadataFrame:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid metadata JSON") from exc
    return parse_metadata_payload(payload)


def parse_metadata_payload(payload: object) -> PoseMetadataFrame:
    if not isinstance(payload, dict):
        raise ValueError("metadata payload must be an object")
    if payload.get("schema") != METADATA_SCHEMA:
        raise ValueError("unsupported metadata schema")

    try:
        return PoseMetadataFrame(
            frame_id=int(payload["frame_id"]),
            created_at_s=float(payload["created_at_s"]),
            width=int(payload["width"]),
            height=int(payload["height"]),
            detections=_parse_detections(payload["detections"]),
            poses=_parse_poses(payload["poses"]),
            gesture=_parse_gesture(payload["gesture"]),
            trigger=_parse_trigger(payload["trigger"]),
            control=_parse_control(payload["control"]),
        )
    except KeyError as exc:
        raise ValueError(f"missing metadata field: {exc.args[0]}") from exc
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("malformed metadata payload") from exc


class MetadataReceiver:
    def __init__(self, bind_host: str, port: int) -> None:
        self._bind_host = bind_host
        self._port = port
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: ReceivedMetadata | None = None

    def start(self) -> None:
        if self._socket is not None:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self._bind_host, self._port))
        sock.settimeout(_SOCKET_TIMEOUT_S)
        self._socket = sock
        self._thread = threading.Thread(target=self._recv_loop, name="dvs-metadata-rx", daemon=True)
        self._thread.start()

    def latest(self) -> ReceivedMetadata | None:
        with self._lock:
            return self._latest

    def close(self) -> None:
        self._stop.set()
        sock = self._socket
        if sock is not None:
            sock.close()
            self._socket = None

    def _recv_loop(self) -> None:
        while not self._stop.is_set():
            sock = self._socket
            if sock is None:
                return
            try:
                data, _addr = sock.recvfrom(_MAX_DATAGRAM_BYTES)
            except TimeoutError:
                continue
            except OSError:
                if self._stop.is_set():
                    return
                continue

            try:
                frame = decode_metadata(data)
            except ValueError:
                continue
            received = ReceivedMetadata(frame=frame, received_at_s=time.monotonic())
            with self._lock:
                self._latest = received


def _parse_detections(value: object) -> tuple[MetadataDetection, ...]:
    if not isinstance(value, list):
        raise ValueError("detections must be a list")
    detections: list[MetadataDetection] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("detection must be an object")
        bbox = item.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise ValueError("malformed detection bbox")
        detections.append(
            MetadataDetection(
                class_id=int(item["class_id"]),
                class_name=str(item["class_name"]),
                confidence=float(item["confidence"]),
                bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
            )
        )
    return tuple(detections)


def _parse_poses(value: object) -> tuple[tuple[MetadataLandmark, ...], ...]:
    if not isinstance(value, list):
        raise ValueError("poses must be a list")
    poses: list[tuple[MetadataLandmark, ...]] = []
    for pose in value:
        if not isinstance(pose, list):
            raise ValueError("pose must be a list")
        landmarks: list[MetadataLandmark] = []
        for landmark in pose:
            if not isinstance(landmark, list) or len(landmark) != 4:
                raise ValueError("malformed pose landmark")
            landmarks.append(
                MetadataLandmark(
                    x=float(landmark[0]),
                    y=float(landmark[1]),
                    visibility=float(landmark[2]),
                    z=float(landmark[3]),
                )
            )
        poses.append(tuple(landmarks))
    return tuple(poses)


def _parse_gesture(value: object) -> MetadataGesture:
    if not isinstance(value, dict):
        raise ValueError("gesture must be an object")
    return MetadataGesture(
        raw=str(value["raw"]),
        stable=str(value["stable"]),
        confidence=float(value["confidence"]),
        reason=str(value["reason"]),
    )


def _parse_trigger(value: object) -> MetadataTrigger | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("trigger must be an object")
    return MetadataTrigger(
        direction=str(value["direction"]),
        confidence=float(value["confidence"]),
        source=str(value["source"]),
        reason=str(value["reason"]),
        created_at_s=float(value["created_at_s"]),
    )


def _parse_control(value: object) -> MetadataControl | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("control must be an object")
    return MetadataControl(
        executed=bool(value["executed"]),
        reason=str(value["reason"]),
        target_altitude_m=_optional_float(value["target_altitude_m"]),
        vehicle_mode=_optional_str(value["vehicle_mode"]),
        vehicle_armed=_optional_bool(value["vehicle_armed"]),
        vehicle_altitude_m=_optional_float(value["vehicle_altitude_m"]),
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    return bool(value)
