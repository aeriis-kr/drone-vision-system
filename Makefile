SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

PYTHON_BIN ?= python3
APT_UPGRADE ?= 1
INSTALL_SYSTEM_DEPS ?= 1

STREAM_HOST ?=
BIND_HOST ?= 0.0.0.0
STREAM_PORT ?= 5000
METADATA_HOST ?=
METADATA_PORT ?= 5001
METADATA_STALE_S ?= 1.0
CONTROL_HOST ?=
CONTROL_PORT ?= 5002
CONTROL_TIMEOUT_S ?= 1.0
CONTROL_RESPONSE_TIMEOUT_S ?= 20.0
CONTROL_BIND_HOST ?= 0.0.0.0
WIDTH ?= 1280
HEIGHT ?= 720
FPS ?= 30
BITRATE ?= 3000000
STREAM_FORMAT ?= mpegts
MAVLINK_DEVICE ?= /dev/serial0
MAVLINK_BAUD ?= 57600
AUTO_DRY_RUN ?= 1
MODEL ?= yolo11n.pt
CONF ?= 0.25
IMGSZ ?= 640
DEVICE ?= auto
RX_DISPLAY ?= opencv
NO_INFERENCE ?= 0
INFERENCE_MAX_FRAMES ?=
NO_FPS ?= 0
NO_OVERLAY ?= 0
NO_METADATA ?= 0
CONTAINER_ENGINE ?= $(shell command -v podman >/dev/null 2>&1 && printf podman || printf docker)
SITL_IMAGE ?= drone-vision-ardupilot-sitl
SITL_CONTAINER ?= drone-vision-sitl
SITL_NETWORK ?= host
SITL_SMOKE_HOST ?= 127.0.0.1
SITL_SMOKE_PORT ?= 14551
SITL_QGC_HOST ?= 127.0.0.1
SITL_QGC_PORT ?= 14550
MAVLINK_SITL_DEVICE ?= udpin:127.0.0.1:$(SITL_SMOKE_PORT)

.PHONY: help setup setup-rx setup-pi install install-rx install-pi run-rx run-pose-control-rx run-pi run-inference-pi run-pose-inference-pi run-pose-control-pi run-pose-control-sitl-pi stream-to-rx dry-run-pi dry-run-inference-pi dry-run-pose-inference-pi pixhawk-bench-gate-test-pi takeover-test-pi build-sitl run-sitl sitl-smoke-test-pi sitl-gesture-control-test-pi check lock clean distclean doctor

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
	@printf '%s\n' '  STREAM_HOST=<receiver-ip> make run-inference-pi       Stream video while running Pi-local YOLO object inference'
	@printf '%s\n' '  STREAM_HOST=<receiver-ip> make run-pose-inference-pi  Stream video while running Pi-local YOLO pose inference'
	@printf '%s\n' '  STREAM_HOST=<receiver-ip> make run-pose-control-pi  Hardware UART: pose gestures evaluate/control Pixhawk via MAVLink (AUTO_DRY_RUN=1 by default)'
	@printf '%s\n' '  CONTROL_HOST=<pi-ip> make run-pose-control-rx  RX-local pose inference sends stable gestures to Pi TCP control'
	@printf '%s\n' '  STREAM_HOST=<receiver-ip> make run-pose-control-sitl-pi  SITL UDP: stable UP gestures command LAND via MAVLink'
	@printf '%s\n' '  scripts/stream-to-rx.sh <receiver-ip>'
	@printf '%s\n' '  make run-rx'
	@printf '%s\n' '  make pixhawk-bench-gate-test-pi  Read-only Pixhawk UART gate check for injected UP-to-LAND triggers'
	@printf '%s\n' '  make takeover-test-pi  Manual LOITER->GUIDED->LOITER Pixhawk smoke test'
	@printf '%s\n' '  make build-sitl       Build ArduPilot SITL image with podman/docker'
	@printf '%s\n' '  make run-sitl         Run ArduCopter SITL; default host network sends UDP to QGC 14550'
	@printf '%s\n' '  make sitl-smoke-test-pi  Non-interactive LOITER->GUIDED->LOITER SITL MAVLink smoke test'
	@printf '%s\n' '  make sitl-gesture-control-test-pi  SITL-only UP trigger to LAND mode-change test'
	@printf '%s\n' ''
	@printf '%s\n' 'Common overrides:'
	@printf '%s\n' '  STREAM_PORT=5000 WIDTH=1280 HEIGHT=720 FPS=30 BITRATE=3000000'
	@printf '%s\n' '  STREAM_FORMAT=mpegts|rtp MODEL=yolo11n.pt DEVICE=auto RX_DISPLAY=opencv|none NO_OVERLAY=1'
	@printf '%s\n' '  STREAM_HOST=<receiver-ip> STREAM_PORT=5000 STREAM_FORMAT=mpegts|rtp'
	@printf '%s\n' '  CONTROL_HOST=<pi-ip> CONTROL_PORT=5002 CONTROL_BIND_HOST=0.0.0.0 CONTROL_TIMEOUT_S=1.0 CONTROL_RESPONSE_TIMEOUT_S=20.0'
	@printf '%s\n' '  INFERENCE_MAX_FRAMES=10 limits Pi-local inference loop during tests'
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

run-inference-pi:
	STREAM_HOST="$(STREAM_HOST)" STREAM_PORT="$(STREAM_PORT)" METADATA_HOST="$(METADATA_HOST)" METADATA_PORT="$(METADATA_PORT)" CONTROL_PORT="$(CONTROL_PORT)" CONTROL_BIND_HOST="$(CONTROL_BIND_HOST)" WIDTH="$(WIDTH)" HEIGHT="$(HEIGHT)" FPS="$(FPS)" BITRATE="$(BITRATE)" STREAM_FORMAT="$(STREAM_FORMAT)" MODEL="$(MODEL)" CONF="$(CONF)" IMGSZ="$(IMGSZ)" DEVICE="$(DEVICE)" NO_INFERENCE="$(NO_INFERENCE)" NO_METADATA="$(NO_METADATA)" INFERENCE_MAX_FRAMES="$(INFERENCE_MAX_FRAMES)" bash scripts/run-inference-pi.sh

run-pose-inference-pi:
	STREAM_HOST="$(STREAM_HOST)" STREAM_PORT="$(STREAM_PORT)" METADATA_HOST="$(METADATA_HOST)" METADATA_PORT="$(METADATA_PORT)" CONTROL_PORT="$(CONTROL_PORT)" CONTROL_BIND_HOST="$(CONTROL_BIND_HOST)" WIDTH="$(WIDTH)" HEIGHT="$(HEIGHT)" FPS="$(FPS)" BITRATE="$(BITRATE)" STREAM_FORMAT="$(STREAM_FORMAT)" MODEL="$(MODEL)" CONF="$(CONF)" IMGSZ="$(IMGSZ)" DEVICE="$(DEVICE)" NO_INFERENCE="$(NO_INFERENCE)" NO_METADATA="$(NO_METADATA)" INFERENCE_MAX_FRAMES="$(INFERENCE_MAX_FRAMES)" bash scripts/run-inference-pi.sh --pose

run-pose-control-pi:
	STREAM_HOST="$(STREAM_HOST)" STREAM_PORT="$(STREAM_PORT)" METADATA_HOST="$(METADATA_HOST)" METADATA_PORT="$(METADATA_PORT)" CONTROL_PORT="$(CONTROL_PORT)" CONTROL_BIND_HOST="$(CONTROL_BIND_HOST)" WIDTH="$(WIDTH)" HEIGHT="$(HEIGHT)" FPS="$(FPS)" BITRATE="$(BITRATE)" STREAM_FORMAT="$(STREAM_FORMAT)" MODEL="$(MODEL)" CONF="$(CONF)" IMGSZ="$(IMGSZ)" DEVICE="$(DEVICE)" NO_INFERENCE="$(NO_INFERENCE)" NO_METADATA="$(NO_METADATA)" INFERENCE_MAX_FRAMES="$(INFERENCE_MAX_FRAMES)" AUTO_DRY_RUN="$(AUTO_DRY_RUN)" bash scripts/run-inference-pi.sh --pose --mavlink-control --mavlink-device "$(MAVLINK_DEVICE)" --mavlink-baud "$(MAVLINK_BAUD)"

run-pose-control-sitl-pi:
	STREAM_HOST="$(STREAM_HOST)" STREAM_PORT="$(STREAM_PORT)" METADATA_HOST="$(METADATA_HOST)" METADATA_PORT="$(METADATA_PORT)" CONTROL_PORT="$(CONTROL_PORT)" CONTROL_BIND_HOST="$(CONTROL_BIND_HOST)" WIDTH="$(WIDTH)" HEIGHT="$(HEIGHT)" FPS="$(FPS)" BITRATE="$(BITRATE)" STREAM_FORMAT="$(STREAM_FORMAT)" MODEL="$(MODEL)" CONF="$(CONF)" IMGSZ="$(IMGSZ)" DEVICE="$(DEVICE)" NO_INFERENCE="$(NO_INFERENCE)" NO_METADATA="$(NO_METADATA)" INFERENCE_MAX_FRAMES="$(INFERENCE_MAX_FRAMES)" AUTO_DRY_RUN="0" bash scripts/run-inference-pi.sh --pose --mavlink-control --mavlink-device "$(MAVLINK_SITL_DEVICE)" --mavlink-baud "$(MAVLINK_BAUD)"

stream-to-rx: run-pi

dry-run-pi:
	STREAM_HOST="192.0.2.1" STREAM_PORT="$(STREAM_PORT)" WIDTH="$(WIDTH)" HEIGHT="$(HEIGHT)" FPS="$(FPS)" BITRATE="$(BITRATE)" STREAM_FORMAT="$(STREAM_FORMAT)" bash scripts/run-pi.sh --dry-run

dry-run-inference-pi:
	STREAM_HOST="192.0.2.1" STREAM_PORT="$(STREAM_PORT)" WIDTH="$(WIDTH)" HEIGHT="$(HEIGHT)" FPS="$(FPS)" BITRATE="$(BITRATE)" STREAM_FORMAT="$(STREAM_FORMAT)" MODEL="$(MODEL)" CONF="$(CONF)" IMGSZ="$(IMGSZ)" DEVICE="$(DEVICE)" NO_INFERENCE="$(NO_INFERENCE)" INFERENCE_MAX_FRAMES="$(INFERENCE_MAX_FRAMES)" bash scripts/run-inference-pi.sh --dry-run

dry-run-pose-inference-pi:
	STREAM_HOST="192.0.2.1" STREAM_PORT="$(STREAM_PORT)" WIDTH="$(WIDTH)" HEIGHT="$(HEIGHT)" FPS="$(FPS)" BITRATE="$(BITRATE)" STREAM_FORMAT="$(STREAM_FORMAT)" MODEL="$(MODEL)" CONF="$(CONF)" IMGSZ="$(IMGSZ)" DEVICE="$(DEVICE)" NO_INFERENCE="$(NO_INFERENCE)" INFERENCE_MAX_FRAMES="$(INFERENCE_MAX_FRAMES)" bash scripts/run-inference-pi.sh --dry-run --pose

pixhawk-bench-gate-test-pi:
	MAVLINK_DEVICE="$(MAVLINK_DEVICE)" MAVLINK_BAUD="$(MAVLINK_BAUD)" bash scripts/pixhawk-bench-gate-test-pi.sh

takeover-test-pi:
	MAVLINK_DEVICE="$(MAVLINK_DEVICE)" MAVLINK_BAUD="$(MAVLINK_BAUD)" bash scripts/takeover-test-pi.sh


build-sitl:
	"$(CONTAINER_ENGINE)" build -f Dockerfile.SITL -t "$(SITL_IMAGE)" .

run-sitl:
	@if [[ "$(SITL_NETWORK)" == "host" ]]; then \
		"$(CONTAINER_ENGINE)" run --rm -it --name "$(SITL_CONTAINER)" --network host -e SITL_SMOKE_HOST="$(SITL_SMOKE_HOST)" -e SITL_SMOKE_PORT="$(SITL_SMOKE_PORT)" -e SITL_QGC_HOST="$(SITL_QGC_HOST)" -e SITL_QGC_PORT="$(SITL_QGC_PORT)" "$(SITL_IMAGE)"; \
	else \
		"$(CONTAINER_ENGINE)" run --rm -it --name "$(SITL_CONTAINER)" -p "$(SITL_QGC_PORT):$(SITL_QGC_PORT)/udp" -p "$(SITL_SMOKE_PORT):$(SITL_SMOKE_PORT)/udp" -e SITL_SMOKE_HOST="$(SITL_SMOKE_HOST)" -e SITL_SMOKE_PORT="$(SITL_SMOKE_PORT)" -e SITL_QGC_HOST="$(SITL_QGC_HOST)" -e SITL_QGC_PORT="$(SITL_QGC_PORT)" "$(SITL_IMAGE)"; \
	fi

sitl-smoke-test-pi:
	MAVLINK_DEVICE="$(MAVLINK_SITL_DEVICE)" MAVLINK_BAUD="$(MAVLINK_BAUD)" bash scripts/sitl-smoke-test-pi.sh

sitl-gesture-control-test-pi:
	MAVLINK_DEVICE="$(MAVLINK_SITL_DEVICE)" MAVLINK_BAUD="$(MAVLINK_BAUD)" bash scripts/sitl-gesture-control-test-pi.sh

run-rx:
	BIND_HOST="$(BIND_HOST)" STREAM_PORT="$(STREAM_PORT)" METADATA_PORT="$(METADATA_PORT)" METADATA_STALE_S="$(METADATA_STALE_S)" CONTROL_HOST="$(CONTROL_HOST)" CONTROL_PORT="$(CONTROL_PORT)" CONTROL_TIMEOUT_S="$(CONTROL_TIMEOUT_S)" CONTROL_RESPONSE_TIMEOUT_S="$(CONTROL_RESPONSE_TIMEOUT_S)" WIDTH="$(WIDTH)" HEIGHT="$(HEIGHT)" FPS="$(FPS)" BITRATE="$(BITRATE)" STREAM_FORMAT="$(STREAM_FORMAT)" MODEL="$(MODEL)" CONF="$(CONF)" IMGSZ="$(IMGSZ)" DEVICE="$(DEVICE)" RX_DISPLAY="$(RX_DISPLAY)" NO_INFERENCE="$(NO_INFERENCE)" NO_FPS="$(NO_FPS)" NO_OVERLAY="$(NO_OVERLAY)" NO_METADATA="$(NO_METADATA)" bash scripts/run-rx.sh

run-pose-control-rx:
	BIND_HOST="$(BIND_HOST)" STREAM_PORT="$(STREAM_PORT)" METADATA_PORT="$(METADATA_PORT)" METADATA_STALE_S="$(METADATA_STALE_S)" CONTROL_HOST="$(CONTROL_HOST)" CONTROL_PORT="$(CONTROL_PORT)" CONTROL_TIMEOUT_S="$(CONTROL_TIMEOUT_S)" CONTROL_RESPONSE_TIMEOUT_S="$(CONTROL_RESPONSE_TIMEOUT_S)" WIDTH="$(WIDTH)" HEIGHT="$(HEIGHT)" FPS="$(FPS)" BITRATE="$(BITRATE)" STREAM_FORMAT="$(STREAM_FORMAT)" MODEL="yolo11n-pose.pt" CONF="$(CONF)" IMGSZ="$(IMGSZ)" DEVICE="$(DEVICE)" RX_DISPLAY="$(RX_DISPLAY)" NO_INFERENCE="$(NO_INFERENCE)" NO_FPS="$(NO_FPS)" NO_OVERLAY="$(NO_OVERLAY)" NO_METADATA="$(NO_METADATA)" bash scripts/run-rx.sh

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
