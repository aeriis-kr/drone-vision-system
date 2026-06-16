#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RX_DIR="$ROOT/vision_rx"

BIND_HOST="${BIND_HOST:-${DVS_BIND_HOST:-0.0.0.0}}"
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
RX_DISPLAY="${RX_DISPLAY:-${DVS_DISPLAY:-opencv}}"
NO_INFERENCE="${NO_INFERENCE:-${DVS_NO_INFERENCE:-0}}"
NO_FPS="${NO_FPS:-${DVS_NO_FPS:-0}}"
NO_OVERLAY="${NO_OVERLAY:-${DVS_NO_OVERLAY:-0}}"
METADATA_PORT="${METADATA_PORT:-${DVS_METADATA_PORT:-5001}}"
METADATA_STALE_S="${METADATA_STALE_S:-${DVS_METADATA_STALE_S:-1.0}}"
NO_METADATA="${NO_METADATA:-${DVS_NO_METADATA:-0}}"
CONTROL_HOST="${CONTROL_HOST:-${DVS_CONTROL_HOST:-${RX_CONTROL_HOST:-}}}"
CONTROL_PORT="${CONTROL_PORT:-${DVS_CONTROL_PORT:-5002}}"
CONTROL_TIMEOUT_S="${CONTROL_TIMEOUT_S:-${DVS_CONTROL_TIMEOUT_S:-1.0}}"
CONTROL_RESPONSE_TIMEOUT_S="${CONTROL_RESPONSE_TIMEOUT_S:-${DVS_CONTROL_RESPONSE_TIMEOUT_S:-20.0}}"

is_truthy() {
	case "$1" in
		1|[Tt][Rr][Uu][Ee]|[Yy][Ee][Ss]|[Yy]|[Oo][Nn])
			return 0
			;;
	esac
	return 1
}

if [[ "$STREAM_FORMAT" == "rtp" ]] && ! is_truthy "$NO_METADATA"; then
	if [[ "$STREAM_PORT" =~ ^[0-9]+$ && "$METADATA_PORT" =~ ^[0-9]+$ ]]; then
		RTP_RTCP_PORT=$((STREAM_PORT + 1))
		if [[ "$METADATA_PORT" == "$STREAM_PORT" || "$METADATA_PORT" == "$RTP_RTCP_PORT" ]]; then
			METADATA_PORT=$((STREAM_PORT + 2))
			printf '[run-rx] RTP reserves UDP ports %s-%s; using METADATA_PORT=%s.\n' \
				"$STREAM_PORT" "$RTP_RTCP_PORT" "$METADATA_PORT" >&2
		fi
	fi
fi



args=(
	--bind-host "$BIND_HOST"
	--port "$STREAM_PORT"
	--width "$WIDTH"
	--height "$HEIGHT"
	--fps "$FPS"
	--format "$STREAM_FORMAT"
	--metadata-port "$METADATA_PORT"
	--metadata-stale-s "$METADATA_STALE_S"
	--model "$MODEL"
	--conf "$CONF"
	--imgsz "$IMGSZ"
	--device "$DEVICE"
	--display "$RX_DISPLAY"
	--control-host "$CONTROL_HOST"
	--control-port "$CONTROL_PORT"
	--control-timeout-s "$CONTROL_TIMEOUT_S"
	--control-response-timeout-s "$CONTROL_RESPONSE_TIMEOUT_S"
)

if is_truthy "$NO_INFERENCE"; then
	args+=(--no-inference)
fi
if is_truthy "$NO_FPS"; then
	args+=(--no-fps)
fi
if is_truthy "$NO_OVERLAY"; then
	args+=(--no-overlay)
fi
if is_truthy "$NO_METADATA"; then
	args+=(--no-metadata)
fi

list_non_loopback_ipv4() {
	if command -v ip >/dev/null 2>&1; then
		ip -o -4 addr show scope global | awk '{ split($4, a, "/"); print $2, a[1] }'
		return
	fi

	if command -v ifconfig >/dev/null 2>&1; then
		ifconfig | awk '
			/^[A-Za-z0-9_.:-]+:/ { iface=$1; sub(":", "", iface) }
			$1 == "inet" && $2 != "127.0.0.1" { print iface, $2 }
		'
		return
	fi

	if command -v hostname >/dev/null 2>&1; then
		hostname -I | tr ' ' '\n' | awk '$1 != "" && $1 !~ /^127\./ { print "unknown", $1 }'
	fi
}

print_pi_stream_commands() {
	local rows ip found
	rows="$(list_non_loopback_ipv4 || true)"
	cat <<EOF

[run-rx] Receiver is about to listen on UDP/RTP port $STREAM_PORT.
[run-rx] Connect this receiver to the same preconfigured AP/network as the Raspberry Pi first.

[run-rx] Non-loopback IPv4 addresses on this receiver:
EOF

	found=0
	while read -r _iface ip; do
		[[ -n "${ip:-}" ]] || continue
		found=1
		printf '  - %s: %s\n' "$_iface" "$ip"
	done <<<"$rows"

	if [[ "$found" == "0" ]]; then
		cat <<EOF
  - none found yet

[run-rx] No receiver IP was detected. Connect to the preconfigured AP/network and run make run-rx again.
EOF
		return
	fi

	cat <<EOF

[run-rx] On the Raspberry Pi repository root, run the command that uses the receiver IP above.
EOF

	while read -r _iface ip; do
		[[ -n "${ip:-}" ]] || continue
		printf '  STREAM_HOST=%s STREAM_PORT=%s WIDTH=%s HEIGHT=%s FPS=%s BITRATE=%s STREAM_FORMAT=%s make run-pi\n' \
			"$ip" "$STREAM_PORT" "$WIDTH" "$HEIGHT" "$FPS" "$BITRATE" "$STREAM_FORMAT"
		printf '  NO_INFERENCE=1 STREAM_HOST=%s STREAM_PORT=%s CONTROL_BIND_HOST=0.0.0.0 CONTROL_PORT=%s WIDTH=%s HEIGHT=%s FPS=%s BITRATE=%s STREAM_FORMAT=%s MAVLINK_DEVICE=/dev/serial0 MAVLINK_BAUD=57600 make run-pose-control-pi\n' \
			"$ip" "$STREAM_PORT" "$CONTROL_PORT" "$WIDTH" "$HEIGHT" "$FPS" "$BITRATE" "$STREAM_FORMAT"
	done <<<"$rows"

	cat <<EOF

[run-rx] For laptop-side pose control, restart this receiver with the Pi IP:
  CONTROL_HOST=<pi-ip> CONTROL_PORT=$CONTROL_PORT CONTROL_RESPONSE_TIMEOUT_S=$CONTROL_RESPONSE_TIMEOUT_S make run-pose-control-rx

[run-rx] Hardware pose control defaults to AUTO_DRY_RUN=1; add AUTO_DRY_RUN=0 only after UART bench gates pass and the vehicle is safe.

[run-rx] Keep this receiver process running, then start the Pi command in another terminal/SSH session.

EOF
}

print_pi_stream_commands

cd "$RX_DIR"
exec uv run vision-rx "${args[@]}" "$@"
