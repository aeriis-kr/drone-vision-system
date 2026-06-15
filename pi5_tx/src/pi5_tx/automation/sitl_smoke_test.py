"""Non-interactive ArduPilot SITL MAVLink smoke test."""

from __future__ import annotations

import argparse
import time

from .config import AutomationConfig
from .gates import HANDOFF_MODE, RETURN_MODE, TAKEOVER_MODE
from .mavlink import PixhawkConnection

DEFAULT_SITL_DEVICE = "udpin:127.0.0.1:14551"


def main() -> int:
    env_config = AutomationConfig.from_env()
    parser = argparse.ArgumentParser(
        description="Non-interactive LOITER -> GUIDED -> LOITER ArduPilot SITL smoke test"
    )
    parser.add_argument("--device", default=DEFAULT_SITL_DEVICE)
    parser.add_argument("--baud", type=int, default=env_config.baud)
    parser.add_argument("--hold-s", type=float, default=1.0)
    parser.add_argument("--connect-timeout-s", type=float, default=30.0)
    parser.add_argument("--mode-timeout-s", type=float, default=10.0)
    parser.add_argument(
        "--skip-stabilize-return",
        action="store_true",
        default=False,
        help="do not send the final post-test STABILIZE safety return",
    )
    args = parser.parse_args()

    try:
        connection = PixhawkConnection.connect(
            args.device,
            args.baud,
            timeout_s=args.connect_timeout_s,
        )
        target = connection.target
        if target is None:
            raise RuntimeError("No ArduPilot heartbeat found")

        print("[sitl-target]")
        print(f"  system   : {target.system}")
        print(f"  component: {target.component}")
        print(f"[sitl-current] {connection.get_mode(timeout_s=args.mode_timeout_s)}")

        if not _set_mode(connection, HANDOFF_MODE, args.mode_timeout_s):
            return 1
        if not _set_mode(connection, TAKEOVER_MODE, args.mode_timeout_s):
            return 1

        print(f"[sitl-hold] {args.hold_s:.1f}s")
        time.sleep(max(0.0, args.hold_s))

        if not _set_mode(connection, RETURN_MODE, args.mode_timeout_s):
            return 1

        if not args.skip_stabilize_return:
            _set_mode(connection, "STABILIZE", args.mode_timeout_s)

        print("[sitl-done]")
        return 0
    except KeyboardInterrupt:
        print("\n[pi5-sitl-smoke-test] cancelled")
        return 130
    except (RuntimeError, ValueError) as exc:
        print(f"[pi5-sitl-smoke-test] error: {exc}")
        return 1


def _set_mode(connection: PixhawkConnection, mode_name: str, timeout_s: float) -> bool:
    print(f"[sitl-mode] {mode_name}")
    if connection.set_mode(mode_name, timeout_s=timeout_s):
        return True
    print(f"[sitl-mode] failed: {mode_name}")
    return False


if __name__ == "__main__":
    raise SystemExit(main())
