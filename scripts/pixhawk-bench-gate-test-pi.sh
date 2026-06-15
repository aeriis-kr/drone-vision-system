#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PI_DIR="$ROOT/pi5_tx"

MAVLINK_DEVICE="${MAVLINK_DEVICE:-${DVS_MAVLINK_DEVICE:-/dev/serial0}}"
MAVLINK_BAUD="${MAVLINK_BAUD:-${DVS_MAVLINK_BAUD:-57600}}"

cd "$PI_DIR"
exec uv run pi5-pixhawk-bench-gate-test --device "$MAVLINK_DEVICE" --baud "$MAVLINK_BAUD" "$@"
