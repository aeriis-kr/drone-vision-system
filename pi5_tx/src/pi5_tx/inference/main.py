"""CLI entrypoint for Pi-local camera-frame inference."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
import time
from typing import Any, Iterable

from pi5_tx.automation.config import AutomationConfig
from pi5_tx.automation.events import TriggerEvent
from pi5_tx.automation.gesture_control import AltitudeControlResult, GestureAltitudeController
from pi5_tx.automation.mavlink import PixhawkConnection
from pi5_tx.automation.remote_control import RemoteControlServerConfig, RemoteControlTCPServer
from pi5_tx.config import StreamConfig
from pi5_tx.inference.config import PiInferenceConfig
from pi5_tx.inference.device import select_device
from pi5_tx.inference.gesture import GestureConfig, GestureDebouncer, classify_vertical_gesture
from pi5_tx.inference.gesture_types import Gesture, GestureDecision, Landmark
from pi5_tx.inference.metadata import (
    MetadataFrame,
    MetadataSenderConfig,
    MetadataUDPSender,
    control_state_from_result,
    trigger_state_from_event,
)
from pi5_tx.inference.pipeline import FramePipelineError, PiInferencePipeline
from pi5_tx.inference.yolo import InferenceError, YoloDetector
from pi5_tx.streamer import RaspberryPiH264Streamer, StreamerError


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "y", "on"}


def build_parser() -> argparse.ArgumentParser:
    stream_defaults = StreamConfig.from_env()
    inference_defaults = PiInferenceConfig.from_env()
    metadata_defaults = MetadataSenderConfig.from_env(stream_defaults.host)
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
    parser.add_argument("--metadata-host", default=metadata_defaults.host)
    parser.add_argument("--metadata-port", type=int, default=metadata_defaults.port)
    parser.add_argument(
        "--no-metadata",
        action="store_false",
        dest="metadata_enabled",
        default=metadata_defaults.enabled,
    )
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
    automation_defaults = AutomationConfig.from_env()
    parser.add_argument(
        "--mavlink-control",
        action="store_true",
        default=False,
        help="execute stable pose gestures as MAVLink altitude steps",
    )
    parser.add_argument("--mavlink-device", default=automation_defaults.device)
    parser.add_argument("--mavlink-baud", type=int, default=automation_defaults.baud)
    parser.add_argument("--mavlink-connect-timeout-s", type=float, default=30.0)
    parser.add_argument(
        "--remote-control-server",
        action="store_true",
        default=_truthy(os.getenv("DVS_REMOTE_CONTROL") or os.getenv("REMOTE_CONTROL")),
        help="listen for receiver-side stable gesture triggers over TCP",
    )
    parser.add_argument(
        "--remote-control-bind-host",
        default=os.getenv("DVS_REMOTE_CONTROL_BIND_HOST")
        or os.getenv("REMOTE_CONTROL_BIND_HOST")
        or os.getenv("CONTROL_BIND_HOST")
        or "0.0.0.0",
    )
    parser.add_argument(
        "--remote-control-port",
        type=int,
        default=int(
            os.getenv("DVS_REMOTE_CONTROL_PORT")
            or os.getenv("REMOTE_CONTROL_PORT")
            or os.getenv("CONTROL_PORT")
            or "5002"
        ),
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
    config = GestureConfig.from_env()
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
    metadata_config = MetadataSenderConfig(
        host=args.metadata_host or stream_config.host,
        port=args.metadata_port,
        enabled=args.metadata_enabled and inference_config.enabled,
    )
    metadata_sender = MetadataUDPSender(metadata_config) if metadata_config.enabled else None
    selected_device = select_device(args.device) if inference_config.enabled else "disabled"

    metadata_status = (
        f"metadata={metadata_config.host}:{metadata_config.port}"
        if metadata_config.enabled
        else "metadata=disabled"
    )
    print(
        "[pi5-inference] "
        f"stream={stream_config.stream_format} "
        f"target={stream_config.host}:{stream_config.port} "
        f"resolution={stream_config.width}x{stream_config.height} "
        f"model={inference_config.model} "
        f"device={selected_device} "
        f"inference={inference_config.enabled} "
        f"{metadata_status}"
    )

    remote_server = None
    try:
        gesture_controller = None
        if args.mavlink_control:
            if not args.pose:
                raise ValueError("--mavlink-control requires --pose")
            automation_config = AutomationConfig.from_env()
            print(
                "[pi5-inference] "
                f"mavlink_control=enabled mavlink={args.mavlink_device} "
                f"dry_run={automation_config.dry_run}"
            )
            gesture_controller = GestureAltitudeController(
                PixhawkConnection.connect(
                    args.mavlink_device,
                    args.mavlink_baud,
                    timeout_s=args.mavlink_connect_timeout_s,
                ),
                automation_config,
            )

        if not inference_config.enabled:
            if args.remote_control_server:
                if gesture_controller is None:
                    raise ValueError("--remote-control-server requires --mavlink-control")
                remote_server = RemoteControlTCPServer(
                    RemoteControlServerConfig(
                        bind_host=args.remote_control_bind_host,
                        port=args.remote_control_port,
                    ),
                    gesture_controller,
                )
                remote_server.start()
            return RaspberryPiH264Streamer(stream_config).run()

        if args.remote_control_server:
            raise ValueError("--remote-control-server requires --no-inference")

        detector = YoloDetector(
            model_name=inference_config.model,
            confidence=inference_config.confidence,
            imgsz=inference_config.imgsz,
            device=selected_device,
            enabled=True,
        )
        pipeline = PiInferencePipeline(stream_config, inference_config)
        return run_loop(
            pipeline.frames(),
            detector,
            inference_config.max_frames,
            gesture_runtime=build_gesture_runtime(args.pose),
            gesture_controller=gesture_controller,
            metadata_sender=metadata_sender,
            frame_width=stream_config.width,
            frame_height=stream_config.height,
        )
    except (FramePipelineError, InferenceError, StreamerError, RuntimeError, ValueError) as exc:
        print(f"[pi5-inference] error: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\n[pi5-inference] stopping")
        return 130
    finally:
        if remote_server is not None:
            remote_server.close()
        if metadata_sender is not None:
            metadata_sender.close()


def run_loop(
    frames: Iterable[Any],
    detector: YoloDetector,
    max_frames: int | None,
    gesture_runtime: GestureRuntime | None = None,
    gesture_controller: GestureAltitudeController | None = None,
    metadata_sender: MetadataUDPSender | None = None,
    frame_width: int | None = None,
    frame_height: int | None = None,
) -> int:
    total_frames = 0
    window_frames = 0
    window_start = time.monotonic()
    latest_trigger: TriggerEvent | None = None
    latest_control: AltitudeControlResult | None = None

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
                    latest_trigger = event
                    print(
                        "[pi5-inference] "
                        f"trigger direction={event.direction} "
                        f"confidence={event.confidence:.2f} "
                        f"source={event.source} "
                        f"reason={event.reason}"
                    )
                    if gesture_controller is not None:
                        control_result = gesture_controller.handle_event(event, now)
                        latest_control = control_result
                        print(
                            "[pi5-inference] "
                            f"control executed={control_result.executed} "
                            f"reason={control_result.reason}"
                        )
        else:
            decision = GestureDecision(Gesture.STOP, 0.0, "gesture disabled")
            stable = Gesture.STOP

        if metadata_sender is not None:
            metadata_sender.send(
                MetadataFrame(
                    frame_id=total_frames,
                    created_at_s=now,
                    width=frame_width or result.frame.shape[1],
                    height=frame_height or result.frame.shape[0],
                    detections=result.detections,
                    poses=result.poses,
                    decision=decision,
                    stable=stable,
                    trigger=trigger_state_from_event(latest_trigger),
                    control=control_state_from_result(latest_control),
                )
            )

        if max_frames is not None and total_frames >= max_frames:
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
