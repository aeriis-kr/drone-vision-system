# pi5_tx

Raspberry Pi 5 transmitter for the Drone Vision System.

Responsibilities are intentionally narrow:

1. Capture from the Raspberry Pi Camera Module with `rpicam-vid`/`libcamera-vid`.
2. Encode H264 with the Raspberry Pi hardware encoder.
3. Stream the compressed video to a receiver over UDP MPEG-TS or RTP.

No YOLO, OpenCV, or inference code belongs in this package.

## Setup on Raspberry Pi 5

From the repository root:

```bash
make setup-pi
```

The setup target:

- updates/upgrades apt packages,
- installs camera, FFmpeg, NetworkManager, Python and uv dependencies,
- creates `uv venv --system-site-packages`,
- asks for explicit confirmation before switching Wi-Fi into AP mode,
- configures a Wi-Fi AP with a randomized SSID,
- prints the SSID/WPA key/Pi AP IP for the receiver user.

Skip AP setup or intentionally bypass the interactive AP prompt if needed:

```bash
CONFIGURE_AP=0 make setup-pi
AP_CONFIRM=1 make setup-pi
```

## Stream to receiver

The receiver prints the exact command to run on the Pi when `make run-rx` starts.
It looks like this:

```bash
STREAM_HOST=10.42.0.123 make run-pi
```

You can also call the convenience wrapper directly:

```bash
scripts/stream-to-rx.sh 10.42.0.123
```

Useful overrides:

```bash
STREAM_HOST=10.42.0.123 STREAM_PORT=5000 WIDTH=1280 HEIGHT=720 FPS=30 BITRATE=3000000 make run-pi
```

For command preview without running hardware:

```bash
make dry-run-pi
```
