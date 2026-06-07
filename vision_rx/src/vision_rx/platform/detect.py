"""Detect the current receiver platform."""

from __future__ import annotations

import importlib
from pathlib import Path
import platform as py_platform
from typing import Any


def detect_backend() -> Any:
    system = py_platform.system().lower()

    if system == "linux" and _is_jetson():
        return _backend("vision_rx.platform.jetson", "JetsonBackend")
    if system == "darwin":
        return _backend("vision_rx.platform.macos", "MacOSBackend")
    if system == "windows":
        return _backend("vision_rx.platform.windows", "WindowsBackend")
    return _backend("vision_rx.platform.linux", "LinuxBackend")


def _is_jetson() -> bool:
    release = py_platform.release().lower()
    return Path("/etc/nv_tegra_release").exists() or "tegra" in release


def _backend(module_name: str, class_name: str) -> Any:
    module = importlib.import_module(module_name)
    return getattr(module, class_name)()
