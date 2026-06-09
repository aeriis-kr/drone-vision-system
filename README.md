# Drone Vision System

Educational drone vision platform split into two independent Python packages:

- `pi5_tx/`: Raspberry Pi 5 camera capture, H264 hardware encode, UDP/RTP transmit.
- `vision_rx/`: FFmpeg receive/decode, YOLO inference, OpenCV visualization.

See `architecture.md` for the design notes.

## Classroom quick start

### 1. Prepare Raspberry Pi 5 and create its Wi-Fi AP

On the Pi:

```bash
make setup-pi
```

This performs apt update/upgrade, installs camera/FFmpeg/Python/uv dependencies,
creates the uv environment, then asks `Switch Wi-Fi into AP mode now? [y/N]`
before switching Wi-Fi into AP mode. If confirmed with `y`, it creates a
randomized SSID such as `DVS-8K2Q7A` and prints the AP connection information.

Useful Pi setup overrides:

```bash
APT_UPGRADE=0 make setup-pi          # skip full-upgrade
WIFI_COUNTRY=KR make setup-pi        # default regulatory country
AP_SSID=DVS-CLASS01 make setup-pi    # optional fixed SSID
AP_PSK=<wpa-key> make setup-pi       # optional fixed WPA key
AP_CONFIRM=1 make setup-pi           # bypass AP safety prompt intentionally
CONFIGURE_AP=0 make setup-pi         # deps only, no AP setup
```

### 2. Connect receiver manually

On the receiver laptop/tablet, manually connect Wi-Fi to the SSID printed by the
Pi setup script.

### 3. Start receiver

On the receiver machine:

```bash
make setup-rx
make run-rx
```

`make run-rx` prints all non-loopback IPv4 addresses on the receiver and prints
one or more exact commands to run on the Pi, for example:

```bash
STREAM_HOST=10.42.0.123 STREAM_PORT=5000 WIDTH=1280 HEIGHT=720 FPS=30 BITRATE=3000000 STREAM_FORMAT=mpegts make run-pi
```

### 4. Start Pi streaming

Copy the command printed by the receiver and run it on the Pi. The Pi then sends
H264 video to the receiver over UDP/RTP.

## Common Make targets

```bash
make help
make check
make dry-run-pi
NO_INFERENCE=1 make run-rx
scripts/stream-to-rx.sh <receiver-ip>
```
