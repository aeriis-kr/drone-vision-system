"""CLI entrypoint for the receiver pipeline."""

from __future__ import annotations

import argparse
import importlib
import time
from typing import Any

from vision_rx.control_client import (
    RemoteControlClient,
    RemoteControlClientConfig,
    RemoteControlError,
    RemoteControlResult,
    RemoteTrigger,
)
from vision_rx.control_overlay import render_control_overlay
from vision_rx.metadata import MetadataReceiver
from vision_rx.metadata_overlay import render_metadata_overlay
from vision_rx.motion import Gesture, GestureConfig, GestureDebouncer, GestureDecision, Landmark, classify_vertical_gesture


class NullDisplay:
    def show(self, _frame: Any) -> bool:
        return True

    def close(self) -> None:
        return None

class GestureRuntime:
    def __init__(self, config: GestureConfig) -> None:
        self.config = config
        self.debouncer = GestureDebouncer(config.debounce_s, config.debounce_missing_grace_s)
        self.stable = Gesture.STOP
        self.latest_decision = GestureDecision(Gesture.STOP, 0.0, "gesture disabled")


def build_gesture_runtime(enabled: bool) -> GestureRuntime | None:
    if not enabled:
        return None
    return GestureRuntime(GestureConfig())

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
    parser.add_argument("--control-host", default=defaults.control_host, help="Pi host for TCP gesture control")
    parser.add_argument("--control-port", type=int, default=defaults.control_port)
    parser.add_argument("--control-timeout-s", type=float, default=defaults.control_timeout_s)
    parser.add_argument(
        "--control-response-timeout-s",
        type=float,
        default=defaults.control_response_timeout_s,
        help="seconds to wait for Pi MAVLink gate/control result after TCP send",
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
        control_host=args.control_host,
        control_port=args.control_port,
        control_timeout_s=args.control_timeout_s,
        control_response_timeout_s=args.control_response_timeout_s,
    )

    metadata_status = f"metadata=:{config.metadata_port}" if config.metadata_enabled else "metadata=disabled"
    control_status = (
        f"control=tcp://{config.control_host}:{config.control_port} "
        f"connect_timeout={config.control_timeout_s:.1f}s "
        f"response_timeout={config.control_response_timeout_s:.1f}s"
        if config.control_host
        else "control=disabled"
    )
    print(
        f"[vision-rx] platform={backend.name} stream={config.stream_format} "
        f"bind={config.bind_host}:{config.port} resolution={config.width}x{config.height} "
        f"device={selected_device} inference={config.inference} overlay={config.render_detections} "
        f"display={config.display} {metadata_status} {control_status}"
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
    control_client = (
        RemoteControlClient(
            RemoteControlClientConfig(
                host=config.control_host,
                port=config.control_port,
                connect_timeout_s=config.control_timeout_s,
                response_timeout_s=config.control_response_timeout_s,
            )
        )
        if config.control_host
        else None
    )
    gesture_runtime = build_gesture_runtime(control_client is not None and config.inference)

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
                control_client=control_client,
                gesture_runtime=gesture_runtime,
                control_host=config.control_host,
                control_port=config.control_port,
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
    control_client: RemoteControlClient | None = None,
    gesture_runtime: GestureRuntime | None = None,
    control_host: str = "",
    control_port: int = 5002,
) -> int:
    last_report = time.monotonic()
    frame_count = 0
    fps = 0.0
    latest_control: RemoteControlResult | None = None
    for frame in receiver.frames():
        frame_count += 1
        now = time.monotonic()
        elapsed = now - last_report
        if elapsed >= 1.0:
            fps = frame_count / elapsed
            frame_count = 0
            last_report = now
            print(f"[vision-rx] fps={fps:.1f}")

        received = (
            None
            if control_client is not None
            else metadata_receiver.latest() if metadata_receiver is not None else None
        )
        if received is None:
            result = detector.detect(frame)
            if gesture_runtime is not None and control_client is not None:
                decision = select_gesture_decision(result.poses, gesture_runtime.config)
                previous_stable = gesture_runtime.stable
                stable = gesture_runtime.debouncer.update(decision.gesture, now_s=now)
                gesture_runtime.stable = stable
                gesture_runtime.latest_decision = decision
                if decision.gesture in (Gesture.UP, Gesture.DOWN) or stable != previous_stable:
                    print(
                        "[vision-rx] "
                        f"gesture={decision.gesture} stable={stable} "
                        f"confidence={decision.confidence:.2f} reason={decision.reason}"
                    )
                if stable != previous_stable and stable in (Gesture.UP, Gesture.DOWN):
                    try:
                        latest_control = control_client.send_trigger(
                            RemoteTrigger(
                                direction="UP" if stable is Gesture.UP else "DOWN",
                                confidence=decision.confidence,
                                source="vision-rx-pose",
                                created_at_s=now,
                                reason=decision.reason,
                            )
                        )
                        print(
                            "[vision-rx] "
                            f"remote_control executed={latest_control.executed} "
                            f"reason={latest_control.reason}"
                        )
                    except RemoteControlError as exc:
                        latest_control = RemoteControlResult(False, str(exc))
                        print(f"[vision-rx] remote_control error: {exc}")
            output = (
                detector.render(result.frame, result.detections, result.poses)
                if render_detections
                else result.frame
            )
            if render_detections and gesture_runtime is not None and control_client is not None:
                output = render_control_overlay(
                    output,
                    raw_gesture=str(gesture_runtime.latest_decision.gesture),
                    stable_gesture=str(gesture_runtime.stable),
                    confidence=gesture_runtime.latest_decision.confidence,
                    reason=gesture_runtime.latest_decision.reason,
                    control=latest_control,
                    control_host=control_host,
                    control_port=control_port,
                )
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
