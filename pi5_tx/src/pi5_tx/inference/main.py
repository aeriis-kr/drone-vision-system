"""CLI entrypoint for Pi-local camera-frame inference."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import time
from typing import Any, Iterable

from pi5_tx.automation.events import TriggerEvent
from pi5_tx.config import StreamConfig
from pi5_tx.inference.config import PiInferenceConfig
from pi5_tx.inference.device import select_device
from pi5_tx.inference.gesture import GestureConfig, GestureDebouncer, classify_vertical_gesture
from pi5_tx.inference.gesture_types import Gesture, GestureDecision, Landmark
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

@dataclass(slots=True)
class GestureRuntime:
    config: GestureConfig
    debouncer: GestureDebouncer
    stable: Gesture = Gesture.STOP


def build_gesture_runtime(enabled: bool) -> GestureRuntime | None:
    if not enabled:
        return None
    config = GestureConfig()
    return GestureRuntime(
        config=config,
        debouncer=GestureDebouncer(config.debounce_s, config.debounce_missing_grace_s),
    )


def select_gesture_decision(
    poses: tuple[tuple[Landmark, ...], ...],
    config: GestureConfig,
) -> GestureDecision:
    if not poses:
        return GestureDecision(Gesture.STOP, 0.0, "no pose")

    decisions = tuple(classify_vertical_gesture(pose, config) for pose in poses)
    active = tuple(decision for decision in decisions if decision.gesture in (Gesture.UP, Gesture.DOWN))
    if active:
        gestures = {decision.gesture for decision in active}
        if len(gestures) == 1:
            return max(active, key=lambda decision: decision.confidence)
        return GestureDecision(
            Gesture.STOP,
            min(decision.confidence for decision in active),
            "conflicting person gestures",
        )

    stop_decisions = tuple(decision for decision in decisions if decision.gesture == Gesture.STOP)
    if stop_decisions:
        return max(stop_decisions, key=lambda decision: decision.confidence)

    fallback = max(decisions, key=lambda decision: decision.confidence)
    return GestureDecision(Gesture.STOP, fallback.confidence, fallback.reason)


def trigger_event_from_gesture(
    decision: GestureDecision,
    stable: Gesture,
    now_s: float,
) -> TriggerEvent | None:
    if stable not in (Gesture.UP, Gesture.DOWN):
        return None
    return TriggerEvent(
        direction="UP" if stable is Gesture.UP else "DOWN",
        confidence=decision.confidence,
        source="pi5-inference-pose",
        created_at_s=now_s,
        reason=decision.reason,
    )





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
        return run_loop(
            pipeline.frames(),
            detector,
            inference_config.max_frames,
            gesture_runtime=build_gesture_runtime(args.pose),
        )
    except (FramePipelineError, InferenceError, RuntimeError, ValueError) as exc:
        print(f"[pi5-inference] error: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\n[pi5-inference] stopping")
        return 130


def run_loop(
    frames: Iterable[Any],
    detector: YoloDetector,
    max_frames: int | None,
    gesture_runtime: GestureRuntime | None = None,
) -> int:
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

        if gesture_runtime is not None:
            decision = select_gesture_decision(result.poses, gesture_runtime.config)
            previous_stable = gesture_runtime.stable
            stable = gesture_runtime.debouncer.update(decision.gesture, now_s=now)
            gesture_runtime.stable = stable
            if decision.gesture in (Gesture.UP, Gesture.DOWN) or stable != previous_stable:
                print(
                    "[pi5-inference] "
                    f"gesture={decision.gesture} "
                    f"stable={stable} "
                    f"confidence={decision.confidence:.2f} "
                    f"reason={decision.reason}"
                )
            if stable != previous_stable:
                event = trigger_event_from_gesture(decision, stable, now)
                if event is not None:
                    print(
                        "[pi5-inference] "
                        f"trigger direction={event.direction} "
                        f"confidence={event.confidence:.2f} "
                        f"source={event.source} "
                        f"reason={event.reason}"
                    )

        if max_frames is not None and total_frames >= max_frames:
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
