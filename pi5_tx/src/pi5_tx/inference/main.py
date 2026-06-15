"""CLI entrypoint for Pi-local camera-frame inference."""

from __future__ import annotations

import argparse
import time
from typing import Any, Iterable

from pi5_tx.config import StreamConfig
from pi5_tx.inference.config import PiInferenceConfig
from pi5_tx.inference.device import select_device
from pi5_tx.inference.pipeline import FramePipelineError, PiInferencePipeline
from pi5_tx.inference.yolo import InferenceError, YoloDetector


def build_parser() -> argparse.ArgumentParser:
    stream_defaults = StreamConfig.from_env()
    inference_defaults = PiInferenceConfig.from_env()
    parser = argparse.ArgumentParser(
        description="Stream Raspberry Pi H264 video while running Pi-local YOLO inference.",
    )
    parser.add_argument("--host", default=stream_defaults.host, help="receiver IP/host")
    parser.add_argument("--port", type=int, default=stream_defaults.port, help="receiver UDP/RTP port")
    parser.add_argument("--width", type=int, default=stream_defaults.width)
    parser.add_argument("--height", type=int, default=stream_defaults.height)
    parser.add_argument("--fps", type=int, default=stream_defaults.fps)
    parser.add_argument(
        "--bitrate",
        type=int,
        default=stream_defaults.bitrate,
        help="H264 bitrate in bit/s",
    )
    parser.add_argument(
        "--format",
        dest="stream_format",
        choices=("mpegts", "udp", "rtp"),
        default=stream_defaults.stream_format,
        help="network container: mpegts/udp is easiest; rtp is lower-level RTP H264",
    )
    parser.add_argument(
        "--camera-command",
        default=stream_defaults.camera_command,
        help="override rpicam-vid/libcamera-vid executable path",
    )
    parser.add_argument("--preview", action="store_true", default=stream_defaults.preview)
    parser.add_argument("--dry-run", action="store_true", default=stream_defaults.dry_run)
    parser.add_argument("--model", default=inference_defaults.model)
    parser.add_argument(
        "--pose",
        action="store_true",
        help="use the default YOLO pose model (yolo11n-pose.pt)",
    )
    parser.add_argument("--conf", type=float, default=inference_defaults.confidence)
    parser.add_argument("--imgsz", type=int, default=inference_defaults.imgsz)
    parser.add_argument("--device", default=inference_defaults.device)
    parser.add_argument(
        "--no-inference",
        action="store_true",
        default=not inference_defaults.enabled,
    )
    parser.add_argument("--max-frames", type=int, default=inference_defaults.max_frames)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    stream_config = StreamConfig(
        host=args.host,
        port=args.port,
        width=args.width,
        height=args.height,
        fps=args.fps,
        bitrate=args.bitrate,
        stream_format=args.stream_format,
        camera_command=args.camera_command,
        preview=args.preview,
        dry_run=args.dry_run,
    )
    model_name = "yolo11n-pose.pt" if args.pose else args.model
    inference_config = PiInferenceConfig(
        model=model_name,
        confidence=args.conf,
        imgsz=args.imgsz,
        device=args.device,
        enabled=not args.no_inference,
        max_frames=args.max_frames,
    )
    selected_device = select_device(args.device)

    print(
        "[pi5-inference] "
        f"stream={stream_config.stream_format} "
        f"target={stream_config.host}:{stream_config.port} "
        f"resolution={stream_config.width}x{stream_config.height} "
        f"model={inference_config.model} "
        f"device={selected_device} "
        f"inference={inference_config.enabled}"
    )

    detector = YoloDetector(
        model_name=inference_config.model,
        confidence=inference_config.confidence,
        imgsz=inference_config.imgsz,
        device=selected_device,
        enabled=inference_config.enabled,
    )
    pipeline = PiInferencePipeline(stream_config, inference_config)

    try:
        return run_loop(pipeline.frames(), detector, inference_config.max_frames)
    except (FramePipelineError, InferenceError, RuntimeError, ValueError) as exc:
        print(f"[pi5-inference] error: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\n[pi5-inference] stopping")
        return 130


def run_loop(frames: Iterable[Any], detector: YoloDetector, max_frames: int | None) -> int:
    total_frames = 0
    window_frames = 0
    window_start = time.monotonic()

    for frame in frames:
        result = detector.detect(frame)
        total_frames += 1
        window_frames += 1

        now = time.monotonic()
        elapsed = now - window_start
        if elapsed >= 1.0:
            print(f"[pi5-inference] fps={window_frames / elapsed:.1f} frames={total_frames}")
            window_start = now
            window_frames = 0

        if result.detections:
            detections = " ".join(
                f"{detection.class_name}:{detection.confidence:.2f}@"
                f"{detection.x1:.0f},{detection.y1:.0f},{detection.x2:.0f},{detection.y2:.0f}"
                for detection in result.detections
            )
            print(f"[pi5-inference] detections={detections}")

        if max_frames is not None and total_frames >= max_frames:
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
