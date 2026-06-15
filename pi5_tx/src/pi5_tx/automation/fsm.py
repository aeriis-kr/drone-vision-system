"""Dry-run automation FSM skeleton with no MAVLink side effects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .config import AutomationConfig
from .events import TriggerEvent
from .gates import (
    HANDOFF_MODE,
    PILOT_EMERGENCY_OVERRIDE_MODES,
    RETURN_MODE,
    TAKEOVER_MODE,
    evaluate_takeover_gate,
)
from .state import GateResult, VehicleState


class AutomationState(StrEnum):
    IDLE = "IDLE"
    MONITOR_LOITER = "MONITOR_LOITER"
    MOTION_CANDIDATE = "MOTION_CANDIDATE"
    TAKEOVER = "TAKEOVER"
    EXECUTE = "EXECUTE"
    VERIFY = "VERIFY"
    RETURN = "RETURN"
    COOLDOWN = "COOLDOWN"
    ABORT = "ABORT"


@dataclass(slots=True)
class AutomationFSM:
    config: AutomationConfig
    state: AutomationState = AutomationState.IDLE

    def evaluate_event(
        self, vehicle: VehicleState, event: TriggerEvent, now_s: float
    ) -> GateResult:
        result = evaluate_takeover_gate(vehicle, event, self.config, now_s)
        self.state = (
            AutomationState.MOTION_CANDIDATE
            if result.allowed
            else AutomationState.MONITOR_LOITER
        )
        return result

    def should_abort_for_pilot_override(self, mode: str | None) -> bool:
        return mode in PILOT_EMERGENCY_OVERRIDE_MODES


__all__ = [
    "AutomationFSM",
    "AutomationState",
    "HANDOFF_MODE",
    "PILOT_EMERGENCY_OVERRIDE_MODES",
    "RETURN_MODE",
    "TAKEOVER_MODE",
]
