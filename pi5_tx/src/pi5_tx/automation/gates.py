"""Safety gates for future Pi-owned Pixhawk automation."""

from __future__ import annotations

from .config import AutomationConfig
from .events import TriggerEvent
from .state import GateResult, VehicleState

HANDOFF_MODE = "LOITER"
TAKEOVER_MODE = "GUIDED"
RETURN_MODE = "LOITER"
LAND_MODE = "LAND"
PILOT_EMERGENCY_OVERRIDE_MODES = frozenset({"RTL", "LAND", "BRAKE", "STABILIZE"})


def is_pilot_emergency_override(mode: str | None) -> bool:
    return mode in PILOT_EMERGENCY_OVERRIDE_MODES


def evaluate_takeover_gate(
    state: VehicleState,
    event: TriggerEvent,
    config: AutomationConfig,
    now_s: float,
) -> GateResult:
    if not state.automation_enabled:
        return GateResult(False, "automation disabled")
    if is_pilot_emergency_override(state.mode):
        return GateResult(False, "pilot emergency override active")
    if state.mode != HANDOFF_MODE:
        return GateResult(False, "mode is not LOITER")
    if not state.armed:
        return GateResult(False, "vehicle not armed")
    if state.altitude_m is None:
        return GateResult(False, "altitude unavailable")
    if state.altitude_m < config.min_current_altitude_m:
        return GateResult(False, "altitude below minimum")
    if (
        event.direction == "DOWN"
        and state.altitude_m - config.altitude_step_m < config.min_target_altitude_m
    ):
        return GateResult(False, "target altitude below minimum")
    if not state.ekf_ok:
        return GateResult(False, "ekf unhealthy")
    if not state.gps_ok:
        return GateResult(False, "gps unhealthy")
    if not state.battery_ok:
        return GateResult(False, "battery unhealthy")
    if not state.pilot_stick_idle:
        return GateResult(False, "pilot input active")
    if (
        state.last_auto_action_s is not None
        and now_s - state.last_auto_action_s < config.cooldown_s
    ):
        return GateResult(False, "cooldown active")
    return GateResult(True, "ok")


def evaluate_land_gate(
    state: VehicleState,
    event: TriggerEvent,
    config: AutomationConfig,
    now_s: float,
) -> GateResult:
    if event.direction != "UP":
        return GateResult(False, "DOWN gesture disabled")
    if not state.automation_enabled:
        return GateResult(False, "automation disabled")
    if state.mode == LAND_MODE:
        return GateResult(False, "already LAND")
    if (
        state.last_auto_action_s is not None
        and now_s - state.last_auto_action_s < config.cooldown_s
    ):
        return GateResult(False, "cooldown active")
    return GateResult(True, "ok")
