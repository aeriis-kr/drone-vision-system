"""SITL end-to-end stable gesture to MAVLink altitude-control test."""

from __future__ import annotations

import argparse
from dataclasses import replace
import time

from .config import AutomationConfig
from .events import TriggerEvent
from .gesture_control import SitlGestureAltitudeController, ensure_sitl_handoff_ready
from .mavlink import PixhawkConnection

DEFAULT_SITL_DEVICE = "udpin:127.0.0.1:14551"


def main() -> int:
    env_config = AutomationConfig.from_env()
    parser = argparse.ArgumentParser(
        description="SITL-only stable UP/DOWN gesture to altitude-command test"
    )
    parser.add_argument("--device", default=DEFAULT_SITL_DEVICE)
    parser.add_argument("--baud", type=int, default=env_config.baud)
    parser.add_argument("--connect-timeout-s", type=float, default=30.0)
    parser.add_argument("--mode-timeout-s", type=float, default=30.0)
    parser.add_argument("--start-altitude-m", type=float, default=5.0)
    parser.add_argument("--altitude-step-m", type=float, default=env_config.altitude_step_m)
    parser.add_argument("--min-current-altitude-m", type=float, default=2.0)
    parser.add_argument("--min-target-altitude-m", type=float, default=env_config.min_target_altitude_m)
    parser.add_argument("--cooldown-s", type=float, default=0.0)
    parser.add_argument("--execute-timeout-s", type=float, default=env_config.execute_timeout_s)
    parser.add_argument("--setpoint-rate-hz", type=float, default=env_config.setpoint_rate_hz)
    parser.add_argument(
        "--sequence",
        nargs="+",
        choices=("UP", "DOWN"),
        default=("UP", "DOWN"),
        help="stable gesture sequence to inject after SITL reaches LOITER",
    )
    parser.add_argument(
        "--no-prepare-flight",
        action="store_true",
        default=False,
        help="skip GUIDED arm/takeoff/LOITER setup; vehicle must already satisfy gates",
    )
    parser.add_argument(
        "--skip-land",
        action="store_true",
        default=False,
        help="leave SITL in LOITER instead of commanding LAND at the end",
    )
    args = parser.parse_args()

    config = replace(
        env_config,
        altitude_step_m=args.altitude_step_m,
        min_current_altitude_m=args.min_current_altitude_m,
        min_target_altitude_m=args.min_target_altitude_m,
        cooldown_s=args.cooldown_s,
        execute_timeout_s=args.execute_timeout_s,
        setpoint_rate_hz=args.setpoint_rate_hz,
        dry_run=False,
    )

    try:
        connection = PixhawkConnection.connect(
            args.device,
            args.baud,
            timeout_s=args.connect_timeout_s,
        )
        target = connection.target
        if target is None:
            raise RuntimeError("No ArduPilot heartbeat found")

        print("[sitl-gesture-target]")
        print(f"  system   : {target.system}")
        print(f"  component: {target.component}")

        if not args.no_prepare_flight:
            ensure_sitl_handoff_ready(
                connection,
                start_altitude_m=args.start_altitude_m,
                min_current_altitude_m=config.min_current_altitude_m,
                timeout_s=args.mode_timeout_s,
            )

        controller = SitlGestureAltitudeController(connection, config)
        for direction in args.sequence:
            now_s = time.monotonic()
            event = TriggerEvent(
                direction=direction,
                confidence=1.0,
                source="sitl-stable-gesture-test",
                created_at_s=now_s,
                reason="injected stable gesture",
            )
            result = controller.handle_event(event, now_s)
            if not result.executed:
                print(f"[sitl-gesture-control] blocked: {result.reason}")
                return 1
            if config.cooldown_s > 0.0:
                time.sleep(config.cooldown_s)

        if not args.skip_land:
            connection.set_mode("LAND", timeout_s=args.mode_timeout_s)

        print("[sitl-gesture-control] done")
        return 0
    except KeyboardInterrupt:
        print("\n[pi5-sitl-gesture-control-test] cancelled")
        return 130
    except (RuntimeError, ValueError) as exc:
        print(f"[pi5-sitl-gesture-control-test] error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
