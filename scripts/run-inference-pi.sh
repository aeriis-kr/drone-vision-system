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

MODEL="${MODEL:-${DVS_MODEL:-yolo11n.pt}}"
CONF="${CONF:-${DVS_CONF:-0.25}}"
IMGSZ="${IMGSZ:-${DVS_IMGSZ:-640}}"
DEVICE="${DEVICE:-${DVS_DEVICE:-auto}}"
NO_INFERENCE="${NO_INFERENCE:-${DVS_NO_INFERENCE:-0}}"
INFERENCE_MAX_FRAMES="${INFERENCE_MAX_FRAMES:-${DVS_INFERENCE_MAX_FRAMES:-}}"
DISPLAY_MODEL="$MODEL"

for arg in "$@"; do
	if [[ "$arg" == "--pose" ]]; then
		DISPLAY_MODEL="yolo11n-pose.pt"
		break
	fi
done

if [[ -z "$STREAM_HOST" && $# -gt 0 && "$1" != -* ]]; then
	STREAM_HOST="$1"
	shift
fi

if [[ -z "$STREAM_HOST" ]]; then
	cat >&2 <<EOF
[run-inference-pi] receiver IP is required.

Connect the Pi and receiver to the same preconfigured AP/network, then run on the receiver:
  NO_INFERENCE=1 make run-rx

The receiver terminal will print the exact command to run here, for example:
  STREAM_HOST=<receiver-ip> make run-inference-pi
EOF
	exit 2
fi

if [[ "$STREAM_HOST" == "127.0.0.1" || "$STREAM_HOST" == "localhost" ]]; then
	echo "[run-inference-pi] warning: STREAM_HOST is $STREAM_HOST; set STREAM_HOST=<receiver-ip> for wireless streaming" >&2
fi
METADATA_HOST="${METADATA_HOST:-${DVS_METADATA_HOST:-$STREAM_HOST}}"
METADATA_PORT="${METADATA_PORT:-${DVS_METADATA_PORT:-5001}}"
NO_METADATA="${NO_METADATA:-${DVS_NO_METADATA:-0}}"

args=(
	--host "$STREAM_HOST"
	--port "$STREAM_PORT"
	--width "$WIDTH"
	--height "$HEIGHT"
	--fps "$FPS"
	--bitrate "$BITRATE"
	--format "$STREAM_FORMAT"
	--metadata-host "$METADATA_HOST"
	--metadata-port "$METADATA_PORT"
	--model "$MODEL"
	--conf "$CONF"
	--imgsz "$IMGSZ"
	--device "$DEVICE"
)

case "${NO_INFERENCE,,}" in
	1|true|yes|y|on)
		args+=(--no-inference)
		;;
esac
case "${NO_METADATA,,}" in
	1|true|yes|y|on)
		args+=(--no-metadata)
		;;
esac


if [[ -n "$INFERENCE_MAX_FRAMES" ]]; then
	args+=(--max-frames "$INFERENCE_MAX_FRAMES")
fi

printf '[run-inference-pi] streaming with local inference to %s:%s (%sx%s@%sfps, bitrate=%s, format=%s, model=%s, device=%s)\n' \
	"$STREAM_HOST" "$STREAM_PORT" "$WIDTH" "$HEIGHT" "$FPS" "$BITRATE" "$STREAM_FORMAT" "$DISPLAY_MODEL" "$DEVICE"

cd "$PI_DIR"
exec uv run pi5-inference "${args[@]}" "$@"
