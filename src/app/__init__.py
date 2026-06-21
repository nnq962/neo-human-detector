"""
Module app chứa các runtime/orchestrator cấp cao.

Runtime ở đây chỉ nối các module nhỏ lại với nhau. Logic YOLO, camera, zone,
output... vẫn nằm ở package chuyên trách tương ứng.
"""

from typing import Any


__all__ = [
    "DetectOnlyRuntime",
    "DetectRuntimeConfig",
    "RuntimeState",
    "run_detect_from_config",
]


# ─────────────────────────────────────────────────────────────────────────────
def __getattr__(name: str) -> Any:
    """Lazy import public API để tránh kéo OpenCV/Ultralytics khi chỉ cần state."""
    if name in {"DetectOnlyRuntime", "DetectRuntimeConfig", "run_detect_from_config"}:
        from src.app.detect_runtime_legacy import (
            DetectOnlyRuntime,
            DetectRuntimeConfig,
            run_detect_from_config,
        )

        return {
            "DetectOnlyRuntime": DetectOnlyRuntime,
            "DetectRuntimeConfig": DetectRuntimeConfig,
            "run_detect_from_config": run_detect_from_config,
        }[name]

    if name == "RuntimeState":
        from src.app.runtime_state import RuntimeState

        return RuntimeState

    raise AttributeError(f"module 'src.app' has no attribute '{name}'")
