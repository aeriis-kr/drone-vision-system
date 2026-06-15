"""Single-camera Pi fan-out pipeline for streaming plus local inference frames."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import queue
import subprocess
import threading
from typing import Any, Iterator

from pi5_tx.config import StreamConfig
from pi5_tx.inference.config import PiInferenceConfig
from pi5_tx.streamer import (
    build_destination_url,
    find_camera_command,
    shell_join,
    terminate_process,
)


class FramePipelineError(RuntimeError):
    """Raised when the Pi camera/FFmpeg frame pipeline fails."""


@dataclass(slots=True)
class PiInferencePipeline:
    stream_config: StreamConfig
    inference_config: PiInferenceConfig

    def build_camera_command(self) -> list[str]:
        camera_bin = self.stream_config.camera_command or (
            "rpicam-vid" if self.stream_config.dry_run else find_camera_command()
        )
        cmd = [
            camera_bin,
            "--timeout",
            "0",
            "--codec",
            "h264",
            "--width",
            str(self.stream_config.width),
            "--height",
            str(self.stream_config.height),
            "--framerate",
            str(self.stream_config.fps),
            "--bitrate",
            str(self.stream_config.bitrate),
            "--intra",
            str(self.stream_config.fps),
            "--output",
            "-",
            "--libav-format",
            "h264",
        ]
        if self.stream_config.inline_headers:
            cmd.append("--inline")
        if not self.stream_config.preview:
            cmd.append("--nopreview")
        return cmd

    def build_ffmpeg_command(self) -> list[str]:
        destination = build_destination_url(
            self.stream_config.stream_format,
            self.stream_config.host,
            self.stream_config.port,
        )
        output_format = "rtp" if self.stream_config.stream_format == "rtp" else "mpegts"
        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-fflags",
            "+genpts",
            "-flags",
            "low_delay",
            "-r",
            str(self.stream_config.fps),
            "-f",
            "h264",
            "-i",
            "pipe:0",
            "-map",
            "0:v:0",
            "-an",
            "-c:v",
            "copy",
            "-bsf:v",
            f"setts=ts=N/{self.stream_config.fps}/TB:duration=1/{self.stream_config.fps}/TB",
            "-flush_packets",
            "1",
            "-muxdelay",
            "0",
            "-muxpreload",
            "0",
            "-f",
            output_format,
            destination,
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            f"setpts=N/({self.stream_config.fps}*TB)",
            "-pix_fmt",
            "bgr24",
            "-f",
            "rawvideo",
            "pipe:1",
        ]

    def frames(self) -> Iterator[Any]:
        camera_cmd = self.build_camera_command()
        ffmpeg_cmd = self.build_ffmpeg_command()

        print("[pi5-inference] camera:", shell_join(camera_cmd))
        print("[pi5-inference] ffmpeg:", shell_join(ffmpeg_cmd))

        if self.stream_config.dry_run:
            return

        camera_proc: subprocess.Popen[bytes] | None = None
        ffmpeg_proc: subprocess.Popen[bytes] | None = None
        stop_reader = threading.Event()

        try:
            camera_proc = subprocess.Popen(camera_cmd, stdout=subprocess.PIPE)
            if camera_proc.stdout is None:
                raise FramePipelineError("camera process did not expose stdout")

            ffmpeg_proc = subprocess.Popen(
                ffmpeg_cmd,
                stdin=camera_proc.stdout,
                stdout=subprocess.PIPE,
            )
            camera_proc.stdout.close()
            stdout = ffmpeg_proc.stdout
            if stdout is None:
                raise FramePipelineError("ffmpeg did not expose stdout")

            frame_size = self.stream_config.width * self.stream_config.height * 3
            np = importlib.import_module("numpy")
            latest_frame: queue.Queue[Any | None] = queue.Queue(maxsize=1)

            def read_frames() -> None:
                while not stop_reader.is_set():
                    frame = read_exact(stdout, frame_size)
                    if frame is None:
                        put_latest(latest_frame, None)
                        return

                    image = np.frombuffer(frame, dtype=np.uint8).reshape(
                        (self.stream_config.height, self.stream_config.width, 3)
                    ).copy()
                    put_latest(latest_frame, image)

            reader = threading.Thread(
                target=read_frames,
                name="pi5-inference-frame-reader",
                daemon=True,
            )
            reader.start()

            while True:
                frame = latest_frame.get()
                if frame is None:
                    code = ffmpeg_proc.poll()
                    raise FramePipelineError(f"ffmpeg stream ended (exit={code})")
                yield frame
        except FileNotFoundError as exc:
            raise FramePipelineError(
                f"missing executable: {exc.filename}. Run `make setup-pi` on the Raspberry Pi."
            ) from exc
        finally:
            stop_reader.set()
            terminate_process(ffmpeg_proc)
            terminate_process(camera_proc)


def put_latest(frame_queue: queue.Queue[Any | None], frame: Any | None) -> None:
    try:
        frame_queue.put_nowait(frame)
        return
    except queue.Full:
        pass

    try:
        frame_queue.get_nowait()
    except queue.Empty:
        pass
    frame_queue.put_nowait(frame)


def read_exact(stream: object, size: int) -> bytes | None:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = stream.read(remaining)  # type: ignore[attr-defined]
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
