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

Start the receiver in monitor-only mode so it displays clean video without local receiver inference or overlays:

```bash
NO_INFERENCE=1 NO_OVERLAY=1 make run-rx
```

Then run the Pi-local object inference stream from the Pi:

```bash
STREAM_HOST=<receiver-ip> make run-inference-pi
```

Use pose inference explicitly when you want the pose model instead of the default object detector:

```bash
STREAM_HOST=<receiver-ip> make run-pose-inference-pi
```

`make run-inference-pi` uses `yolo11n.pt` for object detections.
`make run-pose-inference-pi` uses `yolo11n-pose.pt`, converts pose keypoints into UP/DOWN/STOP gesture decisions, debounces UP/DOWN for 3 seconds, and logs `[pi5-inference] gesture=...` plus `[pi5-inference] trigger ...` when a stable UP/DOWN trigger is emitted.
Both commands use one Pi camera owner, stream clean H264 video to the receiver, and decode the same stream to local BGR frames on the Pi for YOLO inference.
The trigger log does not command Pixhawk; MAVLink flight control remains separate until vehicle-state and altitude-command execution are implemented.

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

In another terminal, run the non-interactive MAVLink smoke test against the dedicated UDP smoke-test stream:

```bash
make sitl-smoke-test-pi
```

The SITL test listens on `udpin:127.0.0.1:14551`, then runs LOITER -> GUIDED -> LOITER with an optional STABILIZE return. It validates the pymavlink mode-change path before using UART hardware; it still sends no altitude or movement setpoints. To force Docker or bridge networking, override `CONTAINER_ENGINE=docker` or `SITL_NETWORK=bridge SITL_QGC_HOST=<host-address> SITL_SMOKE_HOST=<host-address>`.

## Pixhawk takeover smoke test

```bash
MAVLINK_DEVICE=/dev/serial0 MAVLINK_BAUD=57600 make takeover-test-pi
```

This performs a manual LOITER -> GUIDED -> LOITER smoke test with an optional
STABILIZE return. It sends no movement setpoints. Run it only with props removed
or in a safe bench/SITL setup.
