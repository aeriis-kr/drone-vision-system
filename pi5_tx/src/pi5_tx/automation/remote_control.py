"""TCP server that executes receiver-side gesture triggers on the Pi."""

from __future__ import annotations

from dataclasses import dataclass
import json
import socket
import threading
import time
from typing import Any

from pi5_tx.automation.events import TriggerEvent
from pi5_tx.automation.gesture_control import AltitudeControlResult, GestureAltitudeController

REMOTE_CONTROL_SCHEMA = "dvs.remote_control.v1"
DEFAULT_CONTROL_PORT = 5002
_MAX_REQUEST_BYTES = 8192


@dataclass(frozen=True, slots=True)
class RemoteControlServerConfig:
    bind_host: str = "0.0.0.0"
    port: int = DEFAULT_CONTROL_PORT
    timeout_s: float = 1.0


class RemoteControlTCPServer:
    """Accept one newline-delimited JSON trigger per TCP connection."""

    def __init__(self, config: RemoteControlServerConfig, controller: GestureAltitudeController) -> None:
        self.config = config
        self.controller = controller
        self._stop = threading.Event()
        self._started = threading.Event()
        self._start_error: BaseException | None = None
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._serve, name="remote-control-tcp", daemon=True)
        self._thread.start()
        if not self._started.wait(timeout=2.0):
            raise RuntimeError("remote control TCP server did not start")
        if self._start_error is not None:
            raise RuntimeError(f"remote control TCP server failed to start: {self._start_error}")

    def close(self) -> None:
        self._stop.set()
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _serve(self) -> None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                self._socket = server
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind((self.config.bind_host, self.config.port))
                server.listen(8)
                server.settimeout(0.2)
                print(f"[remote-control] listening tcp={self.config.bind_host}:{self.config.port}")
                self._started.set()
                while not self._stop.is_set():
                    try:
                        conn, peer = server.accept()
                    except socket.timeout:
                        continue
                    except OSError:
                        if self._stop.is_set():
                            break
                        raise
                    with conn:
                        conn.settimeout(self.config.timeout_s)
                        self._handle_connection(conn, peer)
        except BaseException as exc:
            self._start_error = exc
            self._started.set()
            if not self._stop.is_set():
                raise

    def _handle_connection(self, conn: socket.socket, peer: tuple[str, int]) -> None:
        try:
            request = _recv_request(conn)
            event = _trigger_event_from_payload(request)
            now_s = time.monotonic()
            result = self.controller.handle_event(event, now_s)
            print(
                "[remote-control] "
                f"peer={peer[0]} direction={event.direction} confidence={event.confidence:.2f} "
                f"executed={result.executed} reason={result.reason}"
            )
            response = {"schema": REMOTE_CONTROL_SCHEMA, "ok": True, "control": _control_payload(result)}
        except Exception as exc:  # noqa: BLE001 - keep the control server alive after bad packets.
            print(f"[remote-control] rejected peer={peer[0]} reason={exc}")
            response = {"schema": REMOTE_CONTROL_SCHEMA, "ok": False, "error": str(exc)}
        conn.sendall(json.dumps(response, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n")


def _recv_request(conn: socket.socket) -> dict[str, Any]:
    chunks: list[bytes] = []
    total = 0
    while total < _MAX_REQUEST_BYTES:
        chunk = conn.recv(min(4096, _MAX_REQUEST_BYTES - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if b"\n" in chunk:
            break
    if not chunks:
        raise ValueError("empty request")

    raw = b"".join(chunks).split(b"\n", 1)[0]
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("request must be a JSON object")
    return payload


def _trigger_event_from_payload(payload: dict[str, Any]) -> TriggerEvent:
    if payload.get("schema") != REMOTE_CONTROL_SCHEMA:
        raise ValueError("unexpected schema")
    if payload.get("type") != "trigger":
        raise ValueError("unsupported command type")

    direction = str(payload.get("direction"))
    if direction not in ("UP", "DOWN"):
        raise ValueError("direction must be UP or DOWN")

    confidence = float(payload.get("confidence", 0.0))
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be in [0, 1]")

    return TriggerEvent(
        direction=direction,
        confidence=confidence,
        source=str(payload.get("source") or "vision-rx-pose"),
        created_at_s=float(payload.get("created_at_s", time.monotonic())),
        reason=str(payload.get("reason") or "remote pose trigger"),
    )


def _control_payload(result: AltitudeControlResult) -> dict[str, object]:
    return {
        "executed": result.executed,
        "reason": result.reason,
        "target_altitude_m": result.target_altitude_m,
        "vehicle_mode": result.vehicle_mode,
        "vehicle_armed": result.vehicle_armed,
        "vehicle_altitude_m": result.vehicle_altitude_m,
    }
