"""Read-only Pixhawk UART automation gate bench test."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import time
from typing import cast

from .config import AutomationConfig
from .events import AltitudeDirection, TriggerEvent
from .gates import evaluate_takeover_gate
from .mavlink import PixhawkConnection
from .state import VehicleState


@dataclass(frozen=True, slots=True)
class BenchGateDecision:
    direction: AltitudeDirection
    allowed: bool
    reason: str
    target_altitude_m: float | None


EVENT_SOURCE = "pixhawk-uart-bench-gate-test"
EVENT_REASON = "injected stable gesture"


def evaluate_bench_direction(
    state: VehicleState,
    direction: AltitudeDirection,
    config: AutomationConfig,
    now_s: float,
) -> BenchGateDecision:
    event = TriggerEvent(
        direction=direction,
        confidence=1.0,
        source=EVENT_SOURCE,
        created_at_s=now_s,
        reason=EVENT_REASON,
    )
    gate = evaluate_takeover_gate(state, event, config, now_s)
    target_altitude_m = None
    if gate.allowed and state.altitude_m is not None:
        if direction == "UP":
            target_altitude_m = state.altitude_m + config.altitude_step_m
        else:
            target_altitude_m = max(
                config.min_target_altitude_m,
                state.altitude_m - config.altitude_step_m,
            )
    return BenchGateDecision(direction, gate.allowed, gate.reason, target_altitude_m)


def directions_from_arg(value: str) -> tuple[AltitudeDirection, ...]:
    if value == "BOTH":
        return ("UP", "DOWN")
    return (cast(AltitudeDirection, value),)


def main() -> int:
    env_config = AutomationConfig.from_env()
    parser = argparse.ArgumentParser(
        description="Read-only Pixhawk UART automation gate bench test"
    )
    parser.add_argument("--device", default=env_config.device)
    parser.add_argument("--baud", type=int, default=env_config.baud)
    parser.add_argument("--connect-timeout-s", type=float, default=15.0)
    parser.add_argument("--snapshot-timeout-s", type=float, default=5.0)
    parser.add_argument(
        "--direction",
        choices=("UP", "DOWN", "BOTH"),
        default="BOTH",
    )
    parser.add_argument("--automation-disabled", action="store_true", default=False)
    parser.add_argument("--last-auto-action-age-s", type=float, default=None)
    args = parser.parse_args()

    try:
        config = AutomationConfig.from_env()
        connection = PixhawkConnection.connect(
            args.device,
            args.baud,
            timeout_s=args.connect_timeout_s,
        )
        target = connection.target
        if target is None:
            raise RuntimeError("No ArduPilot heartbeat found")

        print("[pixhawk-bench-target]")
        print(f"  system   : {target.system}")
        print(f"  component: {target.component}")

        now_s = time.monotonic()
        automation_enabled = not args.automation_disabled
        last_auto_action_s = (
            None
            if args.last_auto_action_age_s is None
            else now_s - max(0.0, args.last_auto_action_age_s)
        )
        state = connection.snapshot_vehicle_state(
            automation_enabled=automation_enabled,
            last_auto_action_s=last_auto_action_s,
            pilot_stick_deadband_pwm=config.pilot_stick_deadband_pwm,
            timeout_s=args.snapshot_timeout_s,
            require_health_messages=True,
        )
        altitude = "unknown" if state.altitude_m is None else f"{state.altitude_m:.2f}m"
        print(
            "[pixhawk-bench-state] "
            f"mode={state.mode} "
            f"armed={state.armed} "
            f"altitude={altitude} "
            f"ekf_ok={state.ekf_ok} "
            f"gps_ok={state.gps_ok} "
            f"battery_ok={state.battery_ok} "
            f"pilot_stick_idle={state.pilot_stick_idle} "
            f"automation_enabled={state.automation_enabled}"
        )

        decisions = tuple(
            evaluate_bench_direction(state, direction, config, now_s)
            for direction in directions_from_arg(args.direction)
        )
        for decision in decisions:
            target_altitude = (
                "n/a"
                if decision.target_altitude_m is None
                else f"{decision.target_altitude_m:.2f}"
            )
            print(
                "[pixhawk-bench-gate] "
                f"direction={decision.direction} "
                f"allowed={str(decision.allowed).lower()} "
                f"reason={decision.reason} "
                f"target_altitude_m={target_altitude}"
            )
        return 0 if all(decision.allowed for decision in decisions) else 1
    except KeyboardInterrupt:
        print("\n[pi5-pixhawk-bench-gate-test] cancelled")
        return 130
    except (RuntimeError, ValueError) as exc:
        print(f"[pi5-pixhawk-bench-gate-test] error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
