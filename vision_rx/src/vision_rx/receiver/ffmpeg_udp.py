"""FFmpeg-based UDP/RTP receiver.

FFmpeg decodes H264 and writes raw BGR frames to stdout.  Python reads fixed
size frames, which keeps the receiver independent from OpenCV's platform-specific
VideoCapture behaviour for network streams.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
from typing import Any, Iterator


class ReceiverError(RuntimeError):
    """Raised when FFmpeg cannot receive or decode frames."""


@dataclass
class FFmpegUDPReceiver:
    config: Any

    _process: subprocess.Popen[bytes] | None = None
    _sdp_path: Path | None = None

    def __enter__(self) -> "FFmpegUDPReceiver":
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()

    def start(self) -> None:
        if self._process is not None:
            return

        command = self.build_command()
        print("[vision-rx] ffmpeg:", shell_join(command))
        try:
            self._process = subprocess.Popen(command, stdout=subprocess.PIPE)
        except FileNotFoundError as exc:
            raise ReceiverError(
                "ffmpeg executable not found. Install FFmpeg or run `make setup-rx`."
            ) from exc

    def frames(self) -> Iterator[Any]:
        if self._process is None:
            self.start()
        proc = self._process
        assert proc is not None
        stdout = proc.stdout
        if stdout is None:
            raise ReceiverError("ffmpeg did not expose stdout")

        frame_size = self.config.frame_bytes
        np = importlib.import_module("numpy")
        latest_frame: queue.Queue[Any | None] = queue.Queue(maxsize=1)
        stop_reader = threading.Event()

        def read_frames() -> None:
            while not stop_reader.is_set():
                frame = read_exact(stdout, frame_size)
                if frame is None:
                    put_latest(latest_frame, None)
                    return

                # Copy so OpenCV can draw overlays in-place, and keep only the
                # newest frame so slow YOLO inference does not backpressure
                # FFmpeg's stdout pipe and stall UDP decoding.
                image = np.frombuffer(frame, dtype=np.uint8).reshape(
                    (self.config.height, self.config.width, 3)
                ).copy()
                put_latest(latest_frame, image)

        reader = threading.Thread(target=read_frames, name="vision-rx-ffmpeg-reader", daemon=True)
        reader.start()

        try:
            while True:
                frame = latest_frame.get()
                if frame is None:
                    code = proc.poll()
                    raise ReceiverError(f"ffmpeg stream ended (exit={code})")
                yield frame
        finally:
            stop_reader.set()

    def stop(self) -> None:
        proc = self._process
        self._process = None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)

        if self._sdp_path is not None:
            try:
                self._sdp_path.unlink(missing_ok=True)
            finally:
                self._sdp_path = None

    def build_command(self) -> list[str]:
        common = [
            self.config.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-fflags",
            "+genpts+discardcorrupt",
            "-flags",
            "low_delay",
            "-probesize",
            "1048576",
            "-analyzeduration",
            "1000000",
        ]
        if self.config.stream_format == "rtp":
            common.extend(["-protocol_whitelist", "file,udp,rtp", "-i", str(self._write_sdp())])
        elif self.config.stream_format in {"mpegts", "udp"}:
            common.extend(["-i", self._udp_url()])
        else:
            raise ReceiverError("stream format must be one of: mpegts, udp, rtp")

        common.extend(
            [
                "-vf",
                f"scale={self.config.width}:{self.config.height},setpts=N/({self.config.fps}*TB)",
                "-fps_mode",
                "cfr",
                "-pix_fmt",
                "bgr24",
                "-f",
                "rawvideo",
                "pipe:1",
            ]
        )
        return common

    def _udp_url(self) -> str:
        return (
            f"udp://@{self.config.bind_host}:{self.config.port}"
            "?fifo_size=1000000&overrun_nonfatal=1"
        )

    def _write_sdp(self) -> Path:
        if self._sdp_path is not None:
            return self._sdp_path

        sdp = f"""v=0
o=- 0 0 IN IP4 127.0.0.1
s=Drone Vision System H264 RTP Stream
c=IN IP4 {self.config.bind_host}
t=0 0
m=video {self.config.port} RTP/AVP 96
a=rtpmap:96 H264/90000
a=fmtp:96 packetization-mode=1
"""
        handle = tempfile.NamedTemporaryFile(
            mode="w", prefix="dvs-", suffix=".sdp", delete=False, encoding="utf-8"
        )
        with handle:
            handle.write(sdp)
        self._sdp_path = Path(handle.name)
        return self._sdp_path


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


def shell_join(command: list[str]) -> str:
    return " ".join(subprocess.list2cmdline([part]) for part in command)
