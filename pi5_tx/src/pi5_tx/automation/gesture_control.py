"""SITL-only gesture-triggered altitude controller."""

from __future__ import annotations

from dataclasses import dataclass

from .config import AutomationConfig
from .events import TriggerEvent
from .gates import HANDOFF_MODE, RETURN_MODE, TAKEOVER_MODE, evaluate_takeover_gate
from .mavlink import PixhawkConnection
from .state import VehicleState


@dataclass(frozen=True, slots=True)
class AltitudeControlResult:
    executed: bool
    reason: str
    target_altitude_m: float | None = None


@dataclass(slots=True)
class SitlGestureAltitudeController:
    """Executes one altitude step for each stable UP/DOWN gesture.

    This class is intentionally SITL-scoped. It requires a live MAVLink
    connection, evaluates the same handoff gate used by the dry-run FSM, enters
    GUIDED only for the command burst, then returns the vehicle to LOITER.
    """

    connection: PixhawkConnection
    config: AutomationConfig
    automation_enabled: bool = True
    last_auto_action_s: float | None = None

    def handle_event(self, event: TriggerEvent, now_s: float) -> AltitudeControlResult:
        vehicle = self.snapshot_vehicle()
        gate = evaluate_takeover_gate(vehicle, event, self.config, now_s)
        print(
            "[gesture-control] "
            f"direction={event.direction} "
            f"mode={vehicle.mode} "
            f"armed={vehicle.armed} "
            f"altitude={_format_altitude(vehicle.altitude_m)} "
            f"gate={gate.reason}"
        )
        if not gate.allowed:
            return AltitudeControlResult(False, gate.reason)
        if vehicle.altitude_m is None:
            return AltitudeControlResult(False, "altitude unavailable")

        target_altitude_m = self.target_altitude(vehicle, event)
        if not self.connection.set_mode(TAKEOVER_MODE, timeout_s=self.config.execute_timeout_s):
            return AltitudeControlResult(False, "GUIDED takeover failed")

        self.connection.send_relative_altitude_target(
            target_altitude_m,
            duration_s=self.config.execute_timeout_s,
            rate_hz=self.config.setpoint_rate_hz,
        )
        self.connection.set_mode(RETURN_MODE, timeout_s=self.config.execute_timeout_s)
        self.last_auto_action_s = now_s
        print(
            "[gesture-control] executed "
            f"direction={event.direction} target_altitude_m={target_altitude_m:.2f}"
        )
        return AltitudeControlResult(True, "ok", target_altitude_m)

    def snapshot_vehicle(self) -> VehicleState:
        return self.connection.snapshot_vehicle_state(
            automation_enabled=self.automation_enabled,
            last_auto_action_s=self.last_auto_action_s,
            pilot_stick_deadband_pwm=self.config.pilot_stick_deadband_pwm,
        )

    def target_altitude(self, vehicle: VehicleState, event: TriggerEvent) -> float:
        if vehicle.altitude_m is None:
            raise RuntimeError("altitude unavailable")
        if event.direction == "UP":
            return vehicle.altitude_m + self.config.altitude_step_m
        return max(
            self.config.min_target_altitude_m,
            vehicle.altitude_m - self.config.altitude_step_m,
        )


def ensure_sitl_handoff_ready(
    connection: PixhawkConnection,
    *,
    start_altitude_m: float,
    min_current_altitude_m: float,
    timeout_s: float,
) -> None:
    """Arm/take off SITL and leave it in LOITER for gesture handoff tests."""

    if not connection.set_mode(TAKEOVER_MODE, timeout_s=timeout_s):
        raise RuntimeError("GUIDED setup failed")
    if not connection.arm(timeout_s=timeout_s):
        raise RuntimeError("SITL arm failed")
    if not connection.command_takeoff(start_altitude_m, timeout_s=timeout_s):
        raise RuntimeError("SITL takeoff command rejected")
    if not connection.wait_relative_altitude_at_least(
        max(start_altitude_m, min_current_altitude_m), timeout_s=timeout_s
    ):
        raise RuntimeError("SITL did not reach minimum handoff altitude")
    if not connection.set_mode(HANDOFF_MODE, timeout_s=timeout_s):
        raise RuntimeError("LOITER handoff setup failed")


def _format_altitude(altitude_m: float | None) -> str:
    if altitude_m is None:
        return "unknown"
    return f"{altitude_m:.2f}m"


__all__ = [
    "AltitudeControlResult",
    "SitlGestureAltitudeController",
    "ensure_sitl_handoff_ready",
]
