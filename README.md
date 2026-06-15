# Drone Vision System

Educational drone vision platform split into two independent Python packages:

- `pi5_tx/`: Raspberry Pi 5 camera capture, H264 hardware encode, UDP/RTP transmit.
- `vision_rx/`: FFmpeg receive/decode, YOLO inference, OpenCV visualization.

See `architecture.md` for the design notes.

## Classroom quick start

### 1. Prepare Raspberry Pi 5

The Pi image should already contain the classroom AP/network connection.
This repository does not create an AP, set SSIDs/passwords, or assign static
Wi-Fi IP addresses.

On the Pi:

```bash
make setup-pi
```

This performs apt update/upgrade, installs camera/FFmpeg/Python/uv dependencies,
and creates the uv environment.

Useful Pi setup override:

```bash
APT_UPGRADE=0 make setup-pi          # skip full-upgrade
```

### 2. Connect receiver manually

On the receiver laptop/tablet, manually connect to the same preconfigured
AP/network as the Pi.

### 3. Start receiver

On the receiver machine:

```bash
make setup-rx
make run-rx
```

`make run-rx` prints all non-loopback IPv4 addresses on the receiver and prints
one or more exact commands to run on the Pi, for example:

```bash
STREAM_HOST=<receiver-ip> STREAM_PORT=5000 WIDTH=1280 HEIGHT=720 FPS=30 BITRATE=3000000 STREAM_FORMAT=mpegts make run-pi
```

### 4. Start Pi streaming

Copy the command printed by the receiver and run it on the Pi. The Pi then sends
H264 video to the receiver over UDP/RTP.

## Common Make targets

```bash
make help
make check
make dry-run-pi
STREAM_HOST=<receiver-ip> make run-inference-pi
MAVLINK_DEVICE=/dev/serial0 MAVLINK_BAUD=57600 make takeover-test-pi
NO_INFERENCE=1 make run-rx
scripts/stream-to-rx.sh <receiver-ip>
```
