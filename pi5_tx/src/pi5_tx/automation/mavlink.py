"""Small pymavlink adapter for manual Pixhawk mode handshakes."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any


COPTER_MODES = {
    "STABILIZE": 0,
    "ALT_HOLD": 2,
    "GUIDED": 4,
    "LOITER": 5,
    "LAND": 9,
    "POSHOLD": 16,
    "BRAKE": 17,
}


@dataclass(frozen=True, slots=True)
class MavlinkTarget:
    system: int
    component: int

def _mavutil() -> Any:
    try:
        from pymavlink import mavutil
    except ModuleNotFoundError as exc:
        raise RuntimeError("pymavlink is required for Pixhawk MAVLink access") from exc
    return mavutil


class PixhawkConnection:
    """Connection wrapper that preserves the proven mode-change handshake."""

    def __init__(self, master: Any, target: MavlinkTarget | None = None) -> None:
        self.master = master
        self.target = target

    @classmethod
    def connect(cls, device: str, baud: int) -> "PixhawkConnection":
        mavutil = _mavutil()
        master = mavutil.mavlink_connection(device, baud=baud)
        connection = cls(master)
        connection.target = connection.wait_target()
        return connection

    def wait_target(self, timeout_s: float = 15.0) -> MavlinkTarget:
        mavutil = _mavutil()
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            msg = self.master.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
            if msg is None:
                continue
            if msg.get_srcSystem() == 0:
                continue
            if msg.autopilot != mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA:
                continue
            return MavlinkTarget(msg.get_srcSystem(), msg.get_srcComponent())
        raise RuntimeError("No ArduPilot heartbeat found")

    def get_mode(self, timeout_s: float = 3.0) -> str | None:
        target = self._require_target()
        mavutil = _mavutil()
        deadline = time.monotonic() + timeout_s
        current_mode: str | None = None
        while time.monotonic() < deadline:
            msg = self.master.recv_match(
                type=["HEARTBEAT", "STATUSTEXT"], blocking=True, timeout=1
            )
            if msg is None:
                continue
            msg_type = msg.get_type()
            if msg_type == "STATUSTEXT":
                print(f"[STATUSTEXT] {msg.severity}: {msg.text}")
                continue
            if msg_type == "HEARTBEAT" and msg.get_srcSystem() == target.system:
                current_mode = mavutil.mode_string_v10(msg)
        return current_mode

    def set_mode(self, mode_name: str, timeout_s: float = 5.0) -> bool:
        if mode_name not in COPTER_MODES:
            raise ValueError(f"unsupported copter mode: {mode_name}")

        mavutil = _mavutil()
        target = self._require_target()
        print(f"[set_mode] {mode_name}")
        self.master.mav.set_mode_send(
            target.system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            COPTER_MODES[mode_name],
        )

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            msg = self.master.recv_match(
                type=["HEARTBEAT", "STATUSTEXT", "COMMAND_ACK"],
                blocking=True,
                timeout=1,
            )
            if msg is None:
                continue
            msg_type = msg.get_type()
            if msg_type == "STATUSTEXT":
                print(f"[STATUSTEXT] {msg.severity}: {msg.text}")
                continue
            if msg_type == "HEARTBEAT" and msg.get_srcSystem() == target.system:
                mode = mavutil.mode_string_v10(msg)
                print(f"  mode: {mode}")
                if mode == mode_name:
                    print(f"  ok: {mode_name}")
                    return True
        return False

    def _require_target(self) -> MavlinkTarget:
        if self.target is None:
            raise RuntimeError("No ArduPilot heartbeat found")
        return self.target
