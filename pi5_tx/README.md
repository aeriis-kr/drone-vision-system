# pi5_tx

Raspberry Pi 5 transmitter for the Drone Vision System.

Responsibilities are intentionally narrow:

1. Capture from the Raspberry Pi Camera Module with `rpicam-vid`/`libcamera-vid`.
2. Encode H264 with the Raspberry Pi hardware encoder.
3. Stream the compressed video to a receiver over UDP MPEG-TS or RTP.

The default transmitter remains stream-only; automation modules are inert unless an explicit automation/test command is run.

## Setup on Raspberry Pi 5

From the repository root:

```bash
make setup-pi
```

The setup target:

- updates/upgrades apt packages,
- installs camera, FFmpeg, Python and uv dependencies,
- creates `uv venv --system-site-packages`.

It does not configure Wi-Fi AP mode, SSIDs/passwords, or static IP addresses.
The Pi image is expected to contain the classroom AP/network connection before
this script runs.

## Stream to receiver

The receiver prints the exact command to run on the Pi when `make run-rx` starts.
It looks like this:

```bash
STREAM_HOST=<receiver-ip> make run-pi
```

You can also call the convenience wrapper directly:

```bash
scripts/stream-to-rx.sh <receiver-ip>
```

Useful overrides:

```bash
STREAM_HOST=<receiver-ip> STREAM_PORT=5000 WIDTH=1280 HEIGHT=720 FPS=30 BITRATE=3000000 make run-pi
```

For command preview without running hardware:

```bash
make dry-run-pi
```

## Stream with Pi-local inference

Start the receiver without local receiver inference; leave overlays enabled so RX can render Pi metadata:

```bash
NO_INFERENCE=1 make run-rx
```

RX overlays are drawn from Pi metadata on UDP 5001, so leave NO_OVERLAY unset unless you want clean video only.

Then run the Pi-local object inference stream from the Pi:

```bash
STREAM_HOST=<receiver-ip> make run-inference-pi
```

Use pose inference explicitly when you want the pose model instead of the default object detector:

```bash
STREAM_HOST=<receiver-ip> make run-pose-inference-pi
```

`make run-inference-pi` uses `yolo11n.pt` for object detections.
`make run-pose-inference-pi` uses `yolo11n-pose.pt`, converts pose keypoints into UP/DOWN/STOP gesture decisions, debounces UP/DOWN for 3 seconds, and logs `[pi5-inference] gesture=...`. Only stable DOWN emits a control trigger; UP is intentionally disabled.
Both commands use one Pi camera owner, stream clean H264 video to the receiver, and decode the same stream to local BGR frames on the Pi for YOLO inference.
Use `make run-pose-control-pi` for live Pixhawk UART gesture control. It defaults to `AUTO_DRY_RUN=1`, so stable DOWN triggers produce metadata/control validation without mode changes; actual RTL mode changes are sent only when you explicitly run with `AUTO_DRY_RUN=0`. Use `make run-pose-control-sitl-pi` only with ArduCopter SITL already prepared in LOITER.

## Stream-only Pi with receiver-side pose control

Keep the Pi camera/encoder path but disable Pi YOLO with `NO_INFERENCE=1`. When this is combined with `make run-pose-control-pi`, the Pi starts a small TCP control server and waits for stable DOWN triggers from the receiver:

```bash
NO_INFERENCE=1 STREAM_HOST=<receiver-ip> CONTROL_PORT=5002 make run-pose-control-pi
```

On the receiver, run pose inference locally and point control at the Pi:

```bash
CONTROL_HOST=<pi-ip> CONTROL_PORT=5002 CONTROL_RESPONSE_TIMEOUT_S=20 make run-pose-control-rx
```

The TCP path is only for sparse control triggers and replies. Video stays on UDP/RTP.

`CONTROL_TIMEOUT_S` covers TCP connect/send. `CONTROL_RESPONSE_TIMEOUT_S` covers the Pi-side MAVLink gate/control result; keep it longer than the MAVLink action window so safety-gate denials return as `executed=False` instead of a receiver timeout.

For command preview without running hardware:

```bash
make dry-run-inference-pi
make dry-run-pose-inference-pi
```

## ArduPilot SITL MAVLink smoke test

Build and run the ArduCopter SITL container from the repository root. The Makefile defaults to Podman when available, then Docker:

```bash
make build-sitl
make run-sitl
```

`make run-sitl` uses host networking by default. QGroundControl should listen on UDP `14550`; MAVProxy sends MAVLink to QGroundControl on `127.0.0.1:14550` and to the pymavlink smoke-test UDP listener on `127.0.0.1:14551`. This avoids binding an extra MAVProxy TCP port that can collide with SITL.

The `make run-sitl` terminal stays attached to the MAVProxy prompt, so SITL RC overrides can be typed there directly, for example `rc 3 1500` to center throttle before switching to LOITER.

In another terminal, run the non-interactive MAVLink smoke test against the dedicated UDP smoke-test stream:

```bash
make sitl-smoke-test-pi
```

The SITL test listens on `udpin:127.0.0.1:14551`, then runs LOITER -> GUIDED -> LOITER with an optional STABILIZE return. It validates the pymavlink mode-change path before using UART hardware; it still sends no altitude or movement setpoints. To force Docker or bridge networking, override `CONTAINER_ENGINE=docker` or `SITL_NETWORK=bridge SITL_QGC_HOST=<host-address> SITL_SMOKE_HOST=<host-address>`.

For the first RTL gesture-control check, keep `make run-sitl` running and execute:

```bash
make sitl-gesture-control-test-pi
```

That SITL-only test arms/takes off in GUIDED, leaves the simulated vehicle in LOITER, injects a stable DOWN trigger, switches to RTL, then lands unless `--skip-land` is passed through `scripts/sitl-gesture-control-test-pi.sh`. UP is intentionally disabled.

To drive the same controller from live Pi pose gestures against SITL, leave SITL armed in LOITER first, for example by running the gesture-control test through the script with `--skip-land`, then start:

```bash
STREAM_HOST=<receiver-ip> make run-pose-control-sitl-pi
```

This path uses the SITL UDP listener on `127.0.0.1:14551`; Pixhawk UART hardware uses `make run-pose-control-pi`.

## Pixhawk UART bench gate test

```bash
MAVLINK_DEVICE=/dev/serial0 MAVLINK_BAUD=57600 make pixhawk-bench-gate-test-pi
```

This connects to Pixhawk over UART, reads the current vehicle state, injects the requested stable gesture event in software, evaluates the same DOWN-to-RTL gate used by live control, and prints whether RTL would be requested. It does not arm, take off, land, or send movement setpoints. Exit code is 0 only when every requested direction passes the gate; a blocked gate prints the reason and exits 1.

On MAVLink connect, the Pi requests `GLOBAL_POSITION_INT` at 5 Hz so the log can still show `relative_alt`, but DOWN-to-RTL no longer requires altitude. If the bench gate prints stale-looking mode/armed values, check the Pixhawk UART `SERIALx_*` mapping and compare against QGC on the same MAVLink stream.

Useful pass-through examples:

```bash
scripts/pixhawk-bench-gate-test-pi.sh --direction DOWN
scripts/pixhawk-bench-gate-test-pi.sh --direction UP
scripts/pixhawk-bench-gate-test-pi.sh --automation-disabled
```

## Pixhawk takeover smoke test

```bash
MAVLINK_DEVICE=/dev/serial0 MAVLINK_BAUD=57600 make takeover-test-pi
```

This performs a manual LOITER -> GUIDED -> LOITER smoke test with an optional
STABILIZE return. It sends no movement setpoints. Run it only with props removed
or in a safe bench/SITL setup.

## Pixhawk UART live pose control

1. Run `MAVLINK_DEVICE=/dev/serial0 MAVLINK_BAUD=57600 make pixhawk-bench-gate-test-pi` and require `[pixhawk-bench-gate] direction=DOWN allowed=true ... target_mode=RTL`.
2. Run `NO_INFERENCE=1 make run-rx` on RX.
3. Run `STREAM_HOST=<receiver-ip> MAVLINK_DEVICE=/dev/serial0 MAVLINK_BAUD=57600 make run-pose-control-pi` on Pi for dry-run metadata/control validation. Expected RX HUD: `control executed=False reason=RTL dry run`, with no Pixhawk mode change.
4. Only with props removed or a safe restrained bench and the vehicle in LOITER, run `AUTO_DRY_RUN=0 STREAM_HOST=<receiver-ip> MAVLINK_DEVICE=/dev/serial0 MAVLINK_BAUD=57600 make run-pose-control-pi`. Expected Pi log: `[gesture-control] executed direction=DOWN target_mode=RTL`; expected RX HUD: `control executed=True reason=RTL mode set`.
