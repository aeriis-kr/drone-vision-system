"""NVIDIA Jetson platform backend."""

from __future__ import annotations


class JetsonBackend:
    name = "jetson"
    default_device = "cuda"
    default_display = "opencv"
    notes = "Jetson Linux should use NVIDIA-provided Torch/CUDA packages via system-site-packages."
