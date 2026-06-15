"""Small pymavlink adapter for Pixhawk/SITL mode and altitude commands."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from .state import VehicleState


COPTER_MODES = {
    "STABILIZE": 0,
    "ALT_HOLD": 2,
    "GUIDED": 4,
    "LOITER": 5,
    "LAND": 9,
    "POSHOLD": 16,
    "BRAKE": 17,
}

_POSITION_ONLY_TYPE_MASK = (
    (1 << 3)
    | (1 << 4)
    | (1 << 5)
    | (1 << 6)
    | (1 << 7)
    | (1 << 8)
    | (1 << 10)
    | (1 << 11)
)


@dataclass(frozen=True, slots=True)
class MavlinkTarget:
    system: int
    component: int


@dataclass(frozen=True, slots=True)
class GlobalPosition:
    lat_int: int
    lon_int: int
    relative_altitude_m: float


@dataclass(frozen=True, slots=True)
class MavlinkCommandResult:
    accepted: bool
    result: int | None


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
    def connect(
        cls,
        device: str,
        baud: int,
        timeout_s: float = 15.0,
    ) -> "PixhawkConnection":
        mavutil = _mavutil()
        try:
            master = mavutil.mavlink_connection(device, baud=baud)
        except OSError as exc:
            raise RuntimeError(
                f"Unable to connect to MAVLink device {device}: {exc}"
            ) from exc
        connection = cls(master)
        connection.target = connection.wait_target(timeout_s=timeout_s)
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

    def arm(self, timeout_s: float = 10.0) -> bool:
        mavutil = _mavutil()
        target = self._require_target()
        print("[arm]")
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self.master.mav.command_long_send(
                target.system,
                target.component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                0,
                1,
                0,
                0,
                0,
                0,
                0,
                0,
            )
            remaining_s = max(0.1, deadline - time.monotonic())
            ack = self.wait_command_ack(
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                timeout_s=min(2.0, remaining_s),
            )
            if ack.accepted and self.wait_armed(
                True, timeout_s=min(2.0, max(0.1, deadline - time.monotonic()))
            ):
                return True
            time.sleep(1.0)
        return False

    def wait_armed(self, armed: bool, timeout_s: float = 10.0) -> bool:
        mavutil = _mavutil()
        target = self._require_target()
        deadline = time.monotonic() + timeout_s
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
            if msg_type != "HEARTBEAT" or msg.get_srcSystem() != target.system:
                continue
            is_armed = bool(
                msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
            )
            print(f"  armed: {is_armed}")
            if is_armed == armed:
                return True
        return False

    def command_takeoff(self, altitude_m: float, timeout_s: float = 10.0) -> bool:
        if altitude_m <= 0.0:
            raise ValueError("takeoff altitude must be positive")

        mavutil = _mavutil()
        target = self._require_target()
        print(f"[takeoff] target_altitude_m={altitude_m:.1f}")
        self.master.mav.command_long_send(
            target.system,
            target.component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            altitude_m,
        )
        return self.wait_command_ack(
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, timeout_s=timeout_s
        ).accepted

    def wait_command_ack(
        self, command: int, timeout_s: float = 5.0
    ) -> MavlinkCommandResult:
        mavutil = _mavutil()
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            msg = self.master.recv_match(
                type=["COMMAND_ACK", "STATUSTEXT"], blocking=True, timeout=1
            )
            if msg is None:
                continue
            msg_type = msg.get_type()
            if msg_type == "STATUSTEXT":
                print(f"[STATUSTEXT] {msg.severity}: {msg.text}")
                continue
            if msg.command != command:
                continue
            result = int(msg.result)
            accepted = result in {
                mavutil.mavlink.MAV_RESULT_ACCEPTED,
                mavutil.mavlink.MAV_RESULT_IN_PROGRESS,
            }
            print(f"[command_ack] command={command} result={result}")
            return MavlinkCommandResult(accepted, result)
        return MavlinkCommandResult(False, None)

    def snapshot_vehicle_state(
        self,
        *,
        automation_enabled: bool,
        last_auto_action_s: float | None,
        pilot_stick_deadband_pwm: int,
        timeout_s: float = 2.0,
        require_health_messages: bool = False,
    ) -> VehicleState:
        mavutil = _mavutil()
        target = self._require_target()
        mode: str | None = None
        armed = False
        altitude_m: float | None = None
        gps_ok = True
        ekf_ok = True
        battery_ok = True
        pilot_stick_idle = True
        seen_mode = False
        seen_altitude = False
        seen_gps = False
        seen_ekf = False
        seen_battery = False
        seen_rc = False

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            msg = self.master.recv_match(
                type=[
                    "HEARTBEAT",
                    "GLOBAL_POSITION_INT",
                    "GPS_RAW_INT",
                    "SYS_STATUS",
                    "EKF_STATUS_REPORT",
                    "RC_CHANNELS",
                    "STATUSTEXT",
                ],
                blocking=True,
                timeout=0.25,
            )
            if msg is None:
                continue
            msg_type = msg.get_type()
            if msg_type == "STATUSTEXT":
                print(f"[STATUSTEXT] {msg.severity}: {msg.text}")
                continue
            if msg.get_srcSystem() != target.system:
                continue
            if msg_type == "HEARTBEAT":
                seen_mode = True
                mode = mavutil.mode_string_v10(msg)
                armed = bool(
                    msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                )
            elif msg_type == "GLOBAL_POSITION_INT":
                seen_altitude = True
                altitude_m = msg.relative_alt / 1000.0
            elif msg_type == "GPS_RAW_INT":
                seen_gps = True
                gps_ok = msg.fix_type >= 3
            elif msg_type == "SYS_STATUS" and msg.battery_remaining >= 0:
                seen_battery = True
                battery_ok = msg.battery_remaining > 15
            elif msg_type == "EKF_STATUS_REPORT":
                seen_ekf = True
                ekf_ok = bool(msg.flags)
            elif msg_type == "RC_CHANNELS":
                seen_rc = True
                pilot_stick_idle = _rc_sticks_idle(msg, pilot_stick_deadband_pwm)
            if not require_health_messages and seen_mode and seen_altitude:
                break
            if (
                require_health_messages
                and seen_mode
                and seen_altitude
                and seen_gps
                and seen_ekf
                and seen_battery
                and seen_rc
            ):
                break

        return VehicleState(
            mode=mode,
            armed=armed,
            altitude_m=altitude_m,
            ekf_ok=ekf_ok if seen_ekf or not require_health_messages else False,
            gps_ok=gps_ok if seen_gps or not require_health_messages else False,
            battery_ok=battery_ok if seen_battery or not require_health_messages else False,
            pilot_stick_idle=pilot_stick_idle if seen_rc or not require_health_messages else False,
            automation_enabled=automation_enabled,
            last_auto_action_s=last_auto_action_s,
        )

    def wait_global_position(self, timeout_s: float = 5.0) -> GlobalPosition:
        target = self._require_target()
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            msg = self.master.recv_match(
                type=["GLOBAL_POSITION_INT", "STATUSTEXT"], blocking=True, timeout=1
            )
            if msg is None:
                continue
            msg_type = msg.get_type()
            if msg_type == "STATUSTEXT":
                print(f"[STATUSTEXT] {msg.severity}: {msg.text}")
                continue
            if msg.get_srcSystem() != target.system:
                continue
            return GlobalPosition(
                lat_int=msg.lat,
                lon_int=msg.lon,
                relative_altitude_m=msg.relative_alt / 1000.0,
            )
        raise RuntimeError("No GLOBAL_POSITION_INT received")

    def wait_relative_altitude_at_least(
        self, altitude_m: float, timeout_s: float = 30.0
    ) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            position = self.wait_global_position(timeout_s=1.0)
            print(f"  relative_altitude_m={position.relative_altitude_m:.2f}")
            if position.relative_altitude_m >= altitude_m:
                return True
        return False

    def send_relative_altitude_target(
        self,
        target_altitude_m: float,
        *,
        duration_s: float,
        rate_hz: float,
    ) -> None:
        if target_altitude_m < 0.0:
            raise ValueError("target altitude must be non-negative")
        if rate_hz <= 0.0:
            raise ValueError("setpoint rate must be positive")

        mavutil = _mavutil()
        target = self._require_target()
        position = self.wait_global_position()
        period_s = 1.0 / rate_hz
        deadline = time.monotonic() + duration_s
        print(
            "[altitude_target] "
            f"current={position.relative_altitude_m:.2f}m "
            f"target={target_altitude_m:.2f}m"
        )
        while time.monotonic() < deadline:
            self.master.mav.set_position_target_global_int_send(
                int(time.monotonic() * 1000) & 0xFFFFFFFF,
                target.system,
                target.component,
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                _POSITION_ONLY_TYPE_MASK,
                position.lat_int,
                position.lon_int,
                target_altitude_m,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            )
            time.sleep(period_s)

    def _require_target(self) -> MavlinkTarget:
        if self.target is None:
            raise RuntimeError("No ArduPilot heartbeat found")
        return self.target


def _rc_sticks_idle(msg: Any, deadband_pwm: int) -> bool:
    for field in ("chan1_raw", "chan2_raw", "chan4_raw"):
        value = getattr(msg, field, 0)
        if value <= 0:
            continue
        if abs(value - 1500) > deadband_pwm:
            return False
    return True
