"""CLI entrypoint for the receiver pipeline."""

from __future__ import annotations

import argparse
import importlib
import time
from typing import Any

from vision_rx.metadata import MetadataReceiver
from vision_rx.metadata_overlay import render_metadata_overlay


class NullDisplay:
    def show(self, _frame: Any) -> bool:
        return True

    def close(self) -> None:
        return None


def build_parser() -> argparse.ArgumentParser:
    receiver_config = importlib.import_module("vision_rx.config").ReceiverConfig
    defaults = receiver_config.from_env()
    parser = argparse.ArgumentParser(
        description="Receive Raspberry Pi H264 UDP/RTP stream and run YOLO inference.",
    )
    parser.add_argument("--bind-host", default=defaults.bind_host)
    parser.add_argument("--port", type=int, default=defaults.port)
    parser.add_argument("--width", type=int, default=defaults.width)
    parser.add_argument("--height", type=int, default=defaults.height)
    parser.add_argument("--fps", type=int, default=defaults.fps)
    parser.add_argument(
        "--format",
        dest="stream_format",
        choices=("mpegts", "udp", "rtp"),
        default=defaults.stream_format,
    )
    parser.add_argument("--ffmpeg", dest="ffmpeg_path", default=defaults.ffmpeg_path)
    parser.add_argument("--model", default=defaults.model)
    parser.add_argument("--conf", type=float, default=defaults.confidence)
    parser.add_argument("--imgsz", type=int, default=defaults.imgsz)
    parser.add_argument("--device", default=defaults.device, help="auto, cpu, cuda, mps, or torch device id")
    parser.add_argument(
        "--display",
        choices=("opencv", "none", "rtsp", "webrtc"),
        default=defaults.display,
    )
    parser.add_argument(
        "--no-inference",
        action="store_false",
        dest="inference",
        default=defaults.inference,
        help="decode and display frames without YOLO",
    )
    parser.add_argument(
        "--no-fps",
        action="store_false",
        dest="show_fps",
        default=defaults.show_fps,
    )
    parser.add_argument(
        "--no-overlay",
        action="store_false",
        dest="render_detections",
        default=defaults.render_detections,
        help="run YOLO but display the clean decoded frame without detection boxes",
    )
    parser.add_argument("--metadata-port", type=int, default=defaults.metadata_port)
    parser.add_argument("--metadata-stale-s", type=float, default=defaults.metadata_stale_s)
    parser.add_argument(
        "--no-metadata",
        action="store_false",
        dest="metadata_enabled",
        default=defaults.metadata_enabled,
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    receiver_config = importlib.import_module("vision_rx.config").ReceiverConfig
    select_device = importlib.import_module("vision_rx.inference.device").select_device
    yolo_module = importlib.import_module("vision_rx.inference.yolo")
    platform_module = importlib.import_module("vision_rx.platform")
    receiver_module = importlib.import_module("vision_rx.receiver.ffmpeg_udp")

    selected_device = select_device(args.device)
    backend = platform_module.detect_backend()
    config = receiver_config(
        bind_host=args.bind_host,
        port=args.port,
        width=args.width,
        height=args.height,
        fps=args.fps,
        stream_format=args.stream_format,
        ffmpeg_path=args.ffmpeg_path,
        model=args.model,
        confidence=args.conf,
        imgsz=args.imgsz,
        device=selected_device,
        display=args.display,
        inference=args.inference,
        show_fps=args.show_fps,
        render_detections=args.render_detections,
        metadata_enabled=args.metadata_enabled,
        metadata_port=args.metadata_port,
        metadata_stale_s=args.metadata_stale_s,
    )

    metadata_status = f"metadata=:{config.metadata_port}" if config.metadata_enabled else "metadata=disabled"
    print(
        f"[vision-rx] platform={backend.name} stream={config.stream_format} "
        f"bind={config.bind_host}:{config.port} resolution={config.width}x{config.height} "
        f"device={selected_device} inference={config.inference} overlay={config.render_detections} "
        f"display={config.display} {metadata_status}"
    )

    detector = yolo_module.YoloDetector(
        model_name=config.model,
        confidence=config.confidence,
        imgsz=config.imgsz,
        device=config.device,
        enabled=config.inference,
    )
    display = build_display(config.display)
    metadata_receiver = MetadataReceiver(config.bind_host, config.metadata_port) if config.metadata_enabled else None

    try:
        if metadata_receiver is not None:
            metadata_receiver.start()
        with receiver_module.FFmpegUDPReceiver(config) as receiver:
            return run_loop(
                receiver,
                detector,
                display,
                config.show_fps,
                config.render_detections,
                metadata_receiver=metadata_receiver,
                metadata_stale_s=config.metadata_stale_s,
                metadata_port=config.metadata_port,
            )
    except (receiver_module.ReceiverError, yolo_module.InferenceError, RuntimeError) as exc:
        print(f"[vision-rx] error: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\n[vision-rx] stopping receiver")
        return 130
    finally:
        if metadata_receiver is not None:
            metadata_receiver.close()
        display.close()


def build_display(name: str) -> Any:
    if name == "none":
        return NullDisplay()
    if name == "opencv":
        module = importlib.import_module("vision_rx.display.opencv")
        return module.OpenCVDisplay()
    if name == "rtsp":
        module = importlib.import_module("vision_rx.display.rtsp")
        return module.RTSPDisplay()
    if name == "webrtc":
        module = importlib.import_module("vision_rx.display.webrtc")
        return module.WebRTCDisplay()
    raise ValueError(f"unsupported display backend: {name}")


def run_loop(
    receiver: Any,
    detector: Any,
    display: Any,
    show_fps: bool,
    render_detections: bool,
    metadata_receiver: Any | None = None,
    metadata_stale_s: float = 1.0,
    metadata_port: int = 5001,
) -> int:
    last_report = time.monotonic()
    frame_count = 0
    fps = 0.0

    for frame in receiver.frames():
        frame_count += 1
        now = time.monotonic()
        elapsed = now - last_report
        if elapsed >= 1.0:
            fps = frame_count / elapsed
            frame_count = 0
            last_report = now
            print(f"[vision-rx] fps={fps:.1f}")

        received = metadata_receiver.latest() if metadata_receiver is not None else None
        if received is None:
            result = detector.detect(frame)
            output = detector.render(result.frame, result.detections) if render_detections else result.frame
            if (
                render_detections
                and metadata_receiver is not None
                and getattr(detector, "enabled", False) is False
            ):
                output = render_metadata_overlay(
                    output,
                    None,
                    age_s=None,
                    stale_after_s=metadata_stale_s,
                    waiting=True,
                    metadata_port=metadata_port,
                )
        else:
            output = frame
            if render_detections:
                output = render_metadata_overlay(
                    output,
                    received.frame,
                    age_s=time.monotonic() - received.received_at_s,
                    stale_after_s=metadata_stale_s,
                    metadata_port=metadata_port,
                )

        if show_fps:
            output = draw_fps(output, fps)
        if not display.show(output):
            return 0

    return 0


def draw_fps(frame: Any, fps: float) -> Any:
    try:
        cv2 = importlib.import_module("cv2")
    except ImportError:
        return frame

    if hasattr(frame, "flags") and not frame.flags.writeable:
        frame = frame.copy()

    return cv2.putText(
        frame,
        f"FPS {fps:.1f}",
        (12, 32),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )


if __name__ == "__main__":
    raise SystemExit(main())
