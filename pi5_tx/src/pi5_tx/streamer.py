"""Camera-to-network streamer for Raspberry Pi 5.

The transmitter intentionally does not import OpenCV, Torch, or YOLO.  It only
captures frames with the Raspberry Pi camera stack, encodes them as H264 using
Pi hardware, and forwards the compressed stream over UDP/RTP via FFmpeg.
"""

from __future__ import annotations

from dataclasses import dataclass
import shutil
import signal
import subprocess
from typing import Any, Sequence


class StreamerError(RuntimeError):
    """Raised when a local streaming dependency is missing or exits badly."""


@dataclass
class RaspberryPiH264Streamer:
    """Run rpicam/libcamera and FFmpeg as a low-latency H264 pipeline."""

    config: Any

    def run(self) -> int:
        camera_cmd = self.build_camera_command()
        ffmpeg_cmd = self.build_ffmpeg_command()

        print("[pi5-tx] camera:", shell_join(camera_cmd))
        print("[pi5-tx] ffmpeg:", shell_join(ffmpeg_cmd))

        if self.config.dry_run:
            return 0

        camera_proc: subprocess.Popen[bytes] | None = None
        ffmpeg_proc: subprocess.Popen[bytes] | None = None

        try:
            camera_proc = subprocess.Popen(camera_cmd, stdout=subprocess.PIPE)
            if camera_proc.stdout is None:
                raise StreamerError("camera process did not expose stdout")

            ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=camera_proc.stdout)
            # Let FFmpeg own the pipe.  If FFmpeg exits, the camera process gets
            # SIGPIPE instead of Python keeping the pipe open forever.
            camera_proc.stdout.close()

            return self._wait_until_exit(camera_proc, ffmpeg_proc)
        except FileNotFoundError as exc:
            raise StreamerError(
                f"missing executable: {exc.filename}. Run `make setup-pi` on the Raspberry Pi."
            ) from exc
        except KeyboardInterrupt:
            print("\n[pi5-tx] stopping stream")
            return 130
        finally:
            terminate_process(ffmpeg_proc)
            terminate_process(camera_proc)

    def build_camera_command(self) -> list[str]:
        camera_bin = self.config.camera_command or (
            "rpicam-vid" if self.config.dry_run else find_camera_command()
        )
        cmd = [
            camera_bin,
            "--timeout",
            "0",
            "--codec",
            "h264",
            "--width",
            str(self.config.width),
            "--height",
            str(self.config.height),
            "--framerate",
            str(self.config.fps),
            "--bitrate",
            str(self.config.bitrate),
            "--intra",
            str(self.config.fps),
            "--output",
            "-",
            "--libav-format",
            self.camera_output_format(),
        ]
        if self.config.inline_headers:
            cmd.append("--inline")
        if not self.config.preview:
            cmd.append("--nopreview")
        return cmd

    def build_ffmpeg_command(self) -> list[str]:
        destination = build_destination_url(
            self.config.stream_format,
            self.config.host,
            self.config.port,
        )
        input_format = self.camera_output_format()
        output_format = "rtp" if self.config.stream_format == "rtp" else "mpegts"
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-fflags",
            "+genpts",
            "-flags",
            "low_delay",
        ]
        if input_format == "h264":
            command.extend(["-r", str(self.config.fps)])
        command.extend(
            [
                "-f",
                input_format,
                "-i",
                "pipe:0",
                "-an",
                "-c:v",
                "copy",
            ]
        )
        if input_format == "h264":
            command.extend(
                [
                    "-bsf:v",
                    f"setts=ts=N/{self.config.fps}/TB:duration=1/{self.config.fps}/TB",
                ]
            )
        command.extend(
            [
                "-flush_packets",
                "1",
                "-muxdelay",
                "0",
                "-muxpreload",
                "0",
                "-f",
                output_format,
                destination,
            ]
        )
        return command

    def camera_output_format(self) -> str:
        """Use timestamped MPEG-TS from rpicam for UDP/MPEG-TS streams."""

        if self.config.stream_format == "rtp":
            return "h264"
        return "mpegts"

    @staticmethod
    def _wait_until_exit(
        camera_proc: subprocess.Popen[bytes],
        ffmpeg_proc: subprocess.Popen[bytes],
    ) -> int:
        while True:
            ffmpeg_code = ffmpeg_proc.poll()
            camera_code = camera_proc.poll()

            if ffmpeg_code is not None:
                return ffmpeg_code
            if camera_code is not None:
                # Camera exiting usually means the stream cannot continue.
                return camera_code

            try:
                ffmpeg_proc.wait(timeout=0.5)
                return ffmpeg_proc.returncode or 0
            except subprocess.TimeoutExpired:
                continue


def find_camera_command() -> str:
    """Prefer Bookworm's rpicam-vid, fall back to Bullseye's libcamera-vid."""

    for candidate in ("rpicam-vid", "libcamera-vid"):
        path = shutil.which(candidate)
        if path:
            return path
    raise StreamerError("rpicam-vid/libcamera-vid not found")


def build_destination_url(stream_format: str, host: str, port: int) -> str:
    if stream_format == "rtp":
        return f"rtp://{host}:{port}?pkt_size=1200"
    if stream_format in {"mpegts", "udp"}:
        return f"udp://{host}:{port}?pkt_size=1316"
    raise StreamerError("stream format must be one of: mpegts, udp, rtp")


def terminate_process(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.poll() is not None:
        return

    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


def shell_join(command: Sequence[str]) -> str:
    return " ".join(subprocess.list2cmdline([part]) for part in command)
