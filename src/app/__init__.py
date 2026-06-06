"""
Module app chứa các runtime/orchestrator cấp cao.

Runtime ở đây chỉ nối các module nhỏ lại với nhau. Logic YOLO, camera, zone,
output... vẫn nằm ở package chuyên trách tương ứng.
"""

from src.app.detect_runtime import DetectOnlyRuntime, DetectRuntimeConfig, run_detect_from_config

__all__ = [
    "DetectOnlyRuntime",
    "DetectRuntimeConfig",
    "run_detect_from_config",
]
