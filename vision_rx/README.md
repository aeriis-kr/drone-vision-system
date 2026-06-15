# vision_rx

Cross-platform receiver for the Drone Vision System.

Pipeline:

```text
UDP/RTP receive -> FFmpeg H264 decode -> raw BGR frames -> YOLO -> OpenCV display
```

Supported acceleration is selected at runtime:

1. CUDA when Torch reports CUDA.
2. MPS on Apple Silicon when Torch reports MPS.
3. CPU fallback.

## Setup

From the repository root:

```bash
make setup-rx
```

This installs FFmpeg where possible, installs `uv` if needed, and syncs Python
dependencies in a `uv venv --system-site-packages` environment.

## Classroom run flow

1. Connect this receiver machine manually to the same preconfigured AP/network
   as the Raspberry Pi.
2. Start the receiver:

   ```bash
   make run-rx
   ```

3. The receiver prints all non-loopback IPv4 addresses and exact Pi commands, for
   example:

   ```bash
   STREAM_HOST=<receiver-ip> STREAM_PORT=5000 WIDTH=1280 HEIGHT=720 FPS=30 BITRATE=3000000 STREAM_FORMAT=mpegts make run-pi
   ```

4. Run the command with the receiver IP address on the Raspberry Pi.

Useful overrides:

```bash
STREAM_PORT=5000 WIDTH=1280 HEIGHT=720 MODEL=yolo11n.pt make run-rx
```

Decode/display without YOLO:

```bash
NO_INFERENCE=1 make run-rx
```

Run YOLO while displaying the clean video stream without detection boxes:

```bash
NO_OVERLAY=1 make run-rx
```

Inference code now exposes structured detections through
`vision_rx.inference.YoloDetector.detect()`. Pose landmark gesture helpers are
available under `vision_rx.motion` for the future Pi-side
`landmarks -> gesture -> TriggerEvent` path. Rendering can stay disabled.

If the transmitter uses RTP instead of UDP MPEG-TS, set both sides to RTP:

```bash
STREAM_FORMAT=rtp make run-rx
STREAM_HOST=<receiver-ip> STREAM_FORMAT=rtp make run-pi
```
