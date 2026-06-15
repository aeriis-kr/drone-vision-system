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

The default command uses `yolo11n.pt`. The pose command uses `yolo11n-pose.pt`.
Both commands use one Pi camera owner, stream clean H264 video to the receiver, and decode the same stream to local BGR frames on the Pi for YOLO inference.
They log detections only. They do not create `TriggerEvent`, call MAVLink, or command Pixhawk.

For command preview without running hardware:

```bash
make dry-run-inference-pi
make dry-run-pose-inference-pi
```

## Pixhawk takeover smoke test

```bash
MAVLINK_DEVICE=/dev/serial0 MAVLINK_BAUD=57600 make takeover-test-pi
```

This performs a manual LOITER -> GUIDED -> LOITER smoke test with an optional
STABILIZE return. It sends no movement setpoints. Run it only with props removed
or in a safe bench/SITL setup.
