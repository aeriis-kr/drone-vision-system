#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PI_DIR="$ROOT/pi5_tx"

STREAM_HOST="${STREAM_HOST:-${DVS_TX_HOST:-}}"
STREAM_PORT="${STREAM_PORT:-${DVS_STREAM_PORT:-5000}}"
WIDTH="${WIDTH:-${DVS_WIDTH:-1280}}"
HEIGHT="${HEIGHT:-${DVS_HEIGHT:-720}}"
FPS="${FPS:-${DVS_FPS:-30}}"
BITRATE="${BITRATE:-${DVS_BITRATE:-3000000}}"
STREAM_FORMAT="${STREAM_FORMAT:-${DVS_STREAM_FORMAT:-mpegts}}"

if [[ -z "$STREAM_HOST" && $# -gt 0 && "$1" != -* ]]; then
	STREAM_HOST="$1"
	shift
fi

if [[ -z "$STREAM_HOST" ]]; then
	cat >&2 <<EOF
[run-pi] receiver IP is required.

Connect the Pi and receiver to the same preconfigured AP/network, then run on the receiver:
  make run-rx

The receiver terminal will print the exact command to run here, for example:
  STREAM_HOST=<receiver-ip> make run-pi
EOF
	exit 2
fi

if [[ "$STREAM_HOST" == "127.0.0.1" || "$STREAM_HOST" == "localhost" ]]; then
	echo "[run-pi] warning: STREAM_HOST is $STREAM_HOST; set STREAM_HOST=<receiver-ip> for wireless streaming" >&2
fi

printf '[run-pi] streaming to %s:%s (%sx%s@%sfps, bitrate=%s, format=%s)\n' \
	"$STREAM_HOST" "$STREAM_PORT" "$WIDTH" "$HEIGHT" "$FPS" "$BITRATE" "$STREAM_FORMAT"

cd "$PI_DIR"
exec uv run pi5-tx \
	--host "$STREAM_HOST" \
	--port "$STREAM_PORT" \
	--width "$WIDTH" \
	--height "$HEIGHT" \
	--fps "$FPS" \
	--bitrate "$BITRATE" \
	--format "$STREAM_FORMAT" \
	"$@"
