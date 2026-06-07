"""CLI entrypoint for Raspberry Pi 5 transmission."""

from __future__ import annotations

import argparse
import importlib


def build_parser() -> argparse.ArgumentParser:
    stream_config = importlib.import_module("pi5_tx.config").StreamConfig
    defaults = stream_config.from_env()
    parser = argparse.ArgumentParser(
        description="Transmit Raspberry Pi Camera Module H264 video over UDP/RTP.",
    )
    parser.add_argument("--host", default=defaults.host, help="receiver IP/host")
    parser.add_argument("--port", type=int, default=defaults.port, help="receiver UDP/RTP port")
    parser.add_argument("--width", type=int, default=defaults.width)
    parser.add_argument("--height", type=int, default=defaults.height)
    parser.add_argument("--fps", type=int, default=defaults.fps)
    parser.add_argument("--bitrate", type=int, default=defaults.bitrate, help="H264 bitrate in bit/s")
    parser.add_argument(
        "--format",
        dest="stream_format",
        choices=("mpegts", "udp", "rtp"),
        default=defaults.stream_format,
        help="network container: mpegts/udp is easiest; rtp is lower-level RTP H264",
    )
    parser.add_argument(
        "--camera-command",
        default=defaults.camera_command,
        help="override rpicam-vid/libcamera-vid executable path",
    )
    parser.add_argument("--preview", action="store_true", default=defaults.preview)
    parser.add_argument("--dry-run", action="store_true", default=defaults.dry_run)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    stream_config = importlib.import_module("pi5_tx.config").StreamConfig
    streamer_module = importlib.import_module("pi5_tx.streamer")
    config = stream_config(
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

    try:
        return streamer_module.RaspberryPiH264Streamer(config).run()
    except streamer_module.StreamerError as exc:
        print(f"[pi5-tx] error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
