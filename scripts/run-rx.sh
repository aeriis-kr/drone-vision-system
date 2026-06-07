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

args=(
	--bind-host "$BIND_HOST"
	--port "$STREAM_PORT"
	--width "$WIDTH"
	--height "$HEIGHT"
	--fps "$FPS"
	--format "$STREAM_FORMAT"
	--model "$MODEL"
	--conf "$CONF"
	--imgsz "$IMGSZ"
	--device "$DEVICE"
	--display "$RX_DISPLAY"
)

if [[ "$NO_INFERENCE" == "1" || "$NO_INFERENCE" == "true" ]]; then
	args+=(--no-inference)
fi
if [[ "$NO_FPS" == "1" || "$NO_FPS" == "true" ]]; then
	args+=(--no-fps)
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
[run-rx] Connect this receiver to the Raspberry Pi AP first.

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

[run-rx] No receiver IP was detected. Connect to the Pi AP and run make run-rx again.
EOF
		return
	fi

	cat <<EOF

[run-rx] On the Raspberry Pi repository root, run the command that uses the receiver IP above.
[run-rx] Usually the Pi AP assigns receiver addresses in the 10.42.0.0/24 range.
EOF

	while read -r _iface ip; do
		[[ -n "${ip:-}" ]] || continue
		printf '  STREAM_HOST=%s STREAM_PORT=%s WIDTH=%s HEIGHT=%s FPS=%s BITRATE=%s STREAM_FORMAT=%s make run-pi\n' \
			"$ip" "$STREAM_PORT" "$WIDTH" "$HEIGHT" "$FPS" "$BITRATE" "$STREAM_FORMAT"
	done <<<"$rows"

	cat <<EOF

[run-rx] Keep this receiver process running, then start the Pi command in another terminal/SSH session.

EOF
}

print_pi_stream_commands

cd "$RX_DIR"
exec uv run vision-rx "${args[@]}" "$@"
