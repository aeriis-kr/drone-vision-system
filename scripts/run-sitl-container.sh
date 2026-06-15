#!/usr/bin/env bash
set -euo pipefail

source "$HOME/.profile"
cd "$HOME/ardupilot"

sim_pid=""
cleanup() {
	if [[ -n "$sim_pid" ]]; then
		kill "$sim_pid" >/dev/null 2>&1 || true
		wait "$sim_pid" >/dev/null 2>&1 || true
	fi
}
trap cleanup EXIT INT TERM

./Tools/autotest/sim_vehicle.py -v ArduCopter -f quad --add-param-file="$HOME/sitl-unlimited-battery.parm" --no-mavproxy &
sim_pid="$!"

python3 - <<'PY'
import socket
import time

host = "127.0.0.1"
port = 5760
deadline = time.monotonic() + 120.0
last_error = None
while time.monotonic() < deadline:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            print(f"[sitl-container] SITL master ready on {host}:{port}", flush=True)
            raise SystemExit(0)
    except OSError as exc:
        last_error = exc
        time.sleep(1.0)
raise SystemExit(f"SITL master not ready on {host}:{port}: {last_error}")
PY

exec mavproxy.py \
	--master=tcp:127.0.0.1:5760 \
	--out="udp:${SITL_QGC_HOST:-127.0.0.1}:${SITL_QGC_PORT:-14550}" \
	--out="udp:${SITL_SMOKE_HOST:-127.0.0.1}:${SITL_SMOKE_PORT:-14551}" \
	--retries=120
