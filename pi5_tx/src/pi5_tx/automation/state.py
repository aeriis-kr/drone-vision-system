"""Vehicle state snapshots and gate results for Pi-side automation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VehicleState:
    mode: str | None
    armed: bool
    altitude_m: float | None
    ekf_ok: bool
    gps_ok: bool
    battery_ok: bool
    pilot_stick_idle: bool
    automation_enabled: bool
    last_auto_action_s: float | None


@dataclass(frozen=True, slots=True)
class GateResult:
    allowed: bool
    reason: str
