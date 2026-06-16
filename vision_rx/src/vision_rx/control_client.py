"""TCP client for sending receiver-side gesture triggers to the Pi controller."""

from __future__ import annotations

from dataclasses import dataclass
import json
import socket
from typing import Any

REMOTE_CONTROL_SCHEMA = "dvs.remote_control.v1"
DEFAULT_CONTROL_PORT = 5002
_MAX_RESPONSE_BYTES = 8192


class RemoteControlError(RuntimeError):
    """Raised when a remote control command cannot be delivered or parsed."""


@dataclass(frozen=True, slots=True)
class RemoteControlClientConfig:
    host: str
    port: int = DEFAULT_CONTROL_PORT
    timeout_s: float = 1.0


@dataclass(frozen=True, slots=True)
class RemoteControlResult:
    executed: bool
    reason: str
    target_altitude_m: float | None = None
    vehicle_mode: str | None = None
    vehicle_armed: bool | None = None
    vehicle_altitude_m: float | None = None


@dataclass(frozen=True, slots=True)
class RemoteTrigger:
    direction: str
    confidence: float
    source: str
    created_at_s: float
    reason: str


class RemoteControlClient:
    def __init__(self, config: RemoteControlClientConfig) -> None:
        self.config = config

    def send_trigger(self, trigger: RemoteTrigger) -> RemoteControlResult:
        payload = {
            "schema": REMOTE_CONTROL_SCHEMA,
            "type": "trigger",
            "direction": trigger.direction,
            "confidence": trigger.confidence,
            "source": trigger.source,
            "created_at_s": trigger.created_at_s,
            "reason": trigger.reason,
        }
        request = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"

        try:
            with socket.create_connection(
                (self.config.host, self.config.port),
                timeout=self.config.timeout_s,
            ) as sock:
                sock.settimeout(self.config.timeout_s)
                sock.sendall(request)
                response = _recv_response(sock)
        except OSError as exc:
            raise RemoteControlError(
                f"remote control connect/send failed: {self.config.host}:{self.config.port}: {exc}"
            ) from exc

        return _parse_response(response)


def _recv_response(sock: socket.socket) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total < _MAX_RESPONSE_BYTES:
        chunk = sock.recv(min(4096, _MAX_RESPONSE_BYTES - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if b"\n" in chunk:
            break
    if not chunks:
        raise RemoteControlError("remote control server returned no response")
    return b"".join(chunks).split(b"\n", 1)[0]


def _parse_response(data: bytes) -> RemoteControlResult:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RemoteControlError("remote control server returned malformed JSON") from exc

    if not isinstance(payload, dict) or payload.get("schema") != REMOTE_CONTROL_SCHEMA:
        raise RemoteControlError("remote control server returned unexpected schema")
    if payload.get("ok") is not True:
        error = payload.get("error")
        raise RemoteControlError(str(error or "remote control server rejected command"))

    control = payload.get("control")
    if not isinstance(control, dict):
        raise RemoteControlError("remote control server response omitted control result")

    try:
        return RemoteControlResult(
            executed=bool(control["executed"]),
            reason=str(control["reason"]),
            target_altitude_m=_optional_float(control.get("target_altitude_m")),
            vehicle_mode=_optional_str(control.get("vehicle_mode")),
            vehicle_armed=_optional_bool(control.get("vehicle_armed")),
            vehicle_altitude_m=_optional_float(control.get("vehicle_altitude_m")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RemoteControlError("remote control server returned malformed control result") from exc


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
