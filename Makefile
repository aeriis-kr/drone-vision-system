SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

PYTHON_BIN ?= python3
APT_UPGRADE ?= 1
INSTALL_SYSTEM_DEPS ?= 1

STREAM_HOST ?=
BIND_HOST ?= 0.0.0.0
STREAM_PORT ?= 5000
WIDTH ?= 1280
HEIGHT ?= 720
FPS ?= 30
BITRATE ?= 3000000
STREAM_FORMAT ?= mpegts
MAVLINK_DEVICE ?= /dev/serial0
MAVLINK_BAUD ?= 57600
MODEL ?= yolo11n.pt
CONF ?= 0.25
IMGSZ ?= 640
DEVICE ?= auto
RX_DISPLAY ?= opencv
NO_INFERENCE ?= 0
NO_FPS ?= 0
NO_OVERLAY ?= 0

.PHONY: help setup setup-rx setup-pi install install-rx install-pi run-rx run-pi stream-to-rx dry-run-pi takeover-test-pi check lock clean distclean doctor

help:
	@printf '%s\n' 'Drone Vision System project targets'
	@printf '%s\n' ''
	@printf '%s\n' 'Setup:'
	@printf '%s\n' '  make setup-rx        Install receiver system deps + uv deps on this machine'
	@printf '%s\n' '  make setup-pi        Raspberry Pi 5 system deps + uv deps'
	@printf '%s\n' '  make install         uv sync both packages without apt/brew installs'
	@printf '%s\n' ''
	@printf '%s\n' 'Run:'
	@printf '%s\n' '  STREAM_HOST=<receiver-ip> make run-pi'
	@printf '%s\n' '  scripts/stream-to-rx.sh <receiver-ip>'
	@printf '%s\n' '  make run-rx'
	@printf '%s\n' '  make takeover-test-pi  Manual LOITER->GUIDED->LOITER Pixhawk smoke test'
	@printf '%s\n' ''
	@printf '%s\n' 'Common overrides:'
	@printf '%s\n' '  STREAM_PORT=5000 WIDTH=1280 HEIGHT=720 FPS=30 BITRATE=3000000'
	@printf '%s\n' '  STREAM_FORMAT=mpegts|rtp MODEL=yolo11n.pt DEVICE=auto RX_DISPLAY=opencv|none NO_OVERLAY=1'
	@printf '%s\n' '  STREAM_HOST=<receiver-ip> STREAM_PORT=5000 STREAM_FORMAT=mpegts|rtp'
	@printf '%s\n' ''
	@printf '%s\n' 'Validation/maintenance:'
	@printf '%s\n' '  make check           Compile Python sources and validate TOML'
	@printf '%s\n' '  make lock            Generate uv.lock in each package'
	@printf '%s\n' '  make clean           Remove caches'
	@printf '%s\n' '  make doctor          Show local tool availability'

setup: setup-rx

setup-rx:
	PYTHON_BIN="$(PYTHON_BIN)" INSTALL_SYSTEM_DEPS="$(INSTALL_SYSTEM_DEPS)" bash scripts/setup-rx.sh

setup-pi:
	PYTHON_BIN="$(PYTHON_BIN)" APT_UPGRADE="$(APT_UPGRADE)" bash scripts/setup-pi.sh

install: install-pi install-rx

install-pi:
	cd pi5_tx && uv venv --system-site-packages --python "$(PYTHON_BIN)" && uv sync

install-rx:
	cd vision_rx && uv venv --system-site-packages --python "$(PYTHON_BIN)" && uv sync

run-pi:
	STREAM_HOST="$(STREAM_HOST)" STREAM_PORT="$(STREAM_PORT)" WIDTH="$(WIDTH)" HEIGHT="$(HEIGHT)" FPS="$(FPS)" BITRATE="$(BITRATE)" STREAM_FORMAT="$(STREAM_FORMAT)" bash scripts/run-pi.sh

stream-to-rx: run-pi

dry-run-pi:
	STREAM_HOST="192.0.2.1" STREAM_PORT="$(STREAM_PORT)" WIDTH="$(WIDTH)" HEIGHT="$(HEIGHT)" FPS="$(FPS)" BITRATE="$(BITRATE)" STREAM_FORMAT="$(STREAM_FORMAT)" bash scripts/run-pi.sh --dry-run

takeover-test-pi:
	MAVLINK_DEVICE="$(MAVLINK_DEVICE)" MAVLINK_BAUD="$(MAVLINK_BAUD)" bash scripts/takeover-test-pi.sh

run-rx:
	BIND_HOST="$(BIND_HOST)" STREAM_PORT="$(STREAM_PORT)" WIDTH="$(WIDTH)" HEIGHT="$(HEIGHT)" FPS="$(FPS)" BITRATE="$(BITRATE)" STREAM_FORMAT="$(STREAM_FORMAT)" MODEL="$(MODEL)" CONF="$(CONF)" IMGSZ="$(IMGSZ)" DEVICE="$(DEVICE)" RX_DISPLAY="$(RX_DISPLAY)" NO_INFERENCE="$(NO_INFERENCE)" NO_FPS="$(NO_FPS)" NO_OVERLAY="$(NO_OVERLAY)" bash scripts/run-rx.sh

check:
	python3 -m compileall -q pi5_tx/src vision_rx/src pi5_tx/main.py vision_rx/main.py
	python3 -c 'import pathlib, tomllib; [tomllib.loads(pathlib.Path(p).read_text()) for p in ("pi5_tx/pyproject.toml", "vision_rx/pyproject.toml")]; print("check ok")'

lock:
	cd pi5_tx && uv lock
	cd vision_rx && uv lock

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

distclean: clean
	rm -rf pi5_tx/.venv vision_rx/.venv pi5_tx/uv.lock vision_rx/uv.lock

doctor:
	@printf 'python3: '; command -v python3 || true
	@printf 'uv:      '; command -v uv || true
	@printf 'ffmpeg:  '; command -v ffmpeg || true
	@printf 'rpicam:  '; command -v rpicam-vid || command -v libcamera-vid || true
