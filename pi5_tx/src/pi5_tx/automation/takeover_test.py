"""Manual LOITER -> GUIDED -> LOITER Pixhawk smoke test."""

from __future__ import annotations

import argparse
import time

from .config import AutomationConfig
from .gates import (
    HANDOFF_MODE,
    PILOT_EMERGENCY_OVERRIDE_MODES,
    RETURN_MODE,
    TAKEOVER_MODE,
)
from .mavlink import PixhawkConnection


def main() -> int:
    env_config = AutomationConfig.from_env()
    parser = argparse.ArgumentParser(
        description="Manual LOITER -> GUIDED -> LOITER Pixhawk smoke test"
    )
    parser.add_argument("--device", default=env_config.device)
    parser.add_argument("--baud", type=int, default=env_config.baud)
    parser.add_argument(
        "--skip-stabilize-return",
        action="store_true",
        default=False,
        help="do not send the final post-test STABILIZE safety return",
    )
    args = parser.parse_args()

    try:
        connection = PixhawkConnection.connect(args.device, args.baud)
        target = connection.target
        if target is None:
            raise RuntimeError("No ArduPilot heartbeat found")

        print("[target]")
        print(f"  system   : {target.system}")
        print(f"  component: {target.component}")
        print(f"[current] {connection.get_mode()}")

        print("\n1) LOITER로 진입")
        if not connection.set_mode(HANDOFF_MODE):
            print("LOITER 진입 실패")
            return 1

        print("\n2) 트리거 대기")
        input("Enter 누르면 Pi가 GUIDED takeover 테스트 실행: ")

        current_mode = connection.get_mode()
        if current_mode in PILOT_EMERGENCY_OVERRIDE_MODES:
            print(f"pilot emergency override active: {current_mode}")
            return 1
        if current_mode != HANDOFF_MODE:
            print(f"handoff blocked: current mode is {current_mode}")
            return 1

        print("\n3) GUIDED takeover")
        if not connection.set_mode(TAKEOVER_MODE):
            print("GUIDED 진입 실패")
            return 1

        print("\n4) 자동 제어 구간 시뮬레이션")
        time.sleep(2)

        print("\n5) LOITER로 반납")
        if not connection.set_mode(RETURN_MODE):
            print("LOITER 복귀 실패")
            return 1

        if not args.skip_stabilize_return:
            print("\n6) 안전하게 STABILIZE 복귀")
            connection.set_mode("STABILIZE")

        print("[done]")
        return 0
    except KeyboardInterrupt:
        print("\n[pi5-takeover-test] cancelled")
        return 130
    except (RuntimeError, ValueError) as exc:
        print(f"[pi5-takeover-test] error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
