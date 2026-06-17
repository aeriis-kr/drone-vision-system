"""MAVLink gesture-triggered RTL controller."""

from __future__ import annotations

from dataclasses import dataclass

from .config import AutomationConfig
from .events import TriggerEvent
from .gates import HANDOFF_MODE, RTL_MODE, TAKEOVER_MODE, evaluate_rtl_gate
from .mavlink import PixhawkConnection
from .state import VehicleState


@dataclass(frozen=True, slots=True)
class AltitudeControlResult:
    executed: bool
    reason: str
    target_altitude_m: float | None = None
    vehicle_mode: str | None = None
    vehicle_armed: bool | None = None
    vehicle_altitude_m: float | None = None

@dataclass(slots=True)
class GestureAltitudeController:
    """Executes RTL mode change for each stable DOWN gesture.

    UP is intentionally disabled. STOP never emits a trigger. DOWN requests RTL
    from LOITER and leaves any later intervention to the RC pilot.
    """

    connection: PixhawkConnection
    config: AutomationConfig
    automation_enabled: bool = True
    last_auto_action_s: float | None = None

    def handle_event(self, event: TriggerEvent, now_s: float) -> AltitudeControlResult:
        vehicle = self.snapshot_vehicle()
        gate = evaluate_rtl_gate(vehicle, event, self.config, now_s)
        print(
            "[gesture-control] "
            f"direction={event.direction} "
            f"mode={vehicle.mode} "
            f"armed={vehicle.armed} "
            f"altitude={_format_altitude(vehicle.altitude_m)} "
            f"gate={gate.reason}"
        )
        if not gate.allowed:
            return AltitudeControlResult(
                False,
                gate.reason,
                None,
                vehicle.mode,
                vehicle.armed,
                vehicle.altitude_m,
            )
        if self.config.dry_run:
            return AltitudeControlResult(
                False,
                "RTL dry run",
                None,
                vehicle.mode,
                vehicle.armed,
                vehicle.altitude_m,
            )
        if not self.connection.set_mode(RTL_MODE, timeout_s=self.config.execute_timeout_s):
            return AltitudeControlResult(
                False,
                "RTL mode change failed",
                None,
                vehicle.mode,
                vehicle.armed,
                vehicle.altitude_m,
            )

        self.last_auto_action_s = now_s
        print(f"[gesture-control] executed direction={event.direction} target_mode={RTL_MODE}")
        return AltitudeControlResult(
            True,
            "RTL mode set",
            None,
            vehicle.mode,
            vehicle.armed,
            vehicle.altitude_m,
        )

    def snapshot_vehicle(self) -> VehicleState:
        return self.connection.snapshot_vehicle_state(
            automation_enabled=self.automation_enabled,
            last_auto_action_s=self.last_auto_action_s,
            pilot_stick_deadband_pwm=self.config.pilot_stick_deadband_pwm,
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
    "GestureAltitudeController",
    "ensure_sitl_handoff_ready",
]
