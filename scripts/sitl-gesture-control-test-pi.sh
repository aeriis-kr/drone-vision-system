#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PI_DIR="$ROOT/pi5_tx"

MAVLINK_DEVICE="${MAVLINK_DEVICE:-${DVS_MAVLINK_DEVICE:-udpin:127.0.0.1:14551}}"
MAVLINK_BAUD="${MAVLINK_BAUD:-${DVS_MAVLINK_BAUD:-57600}}"

cd "$PI_DIR"
exec uv run pi5-sitl-gesture-control-test --device "$MAVLINK_DEVICE" --baud "$MAVLINK_BAUD" "$@"
