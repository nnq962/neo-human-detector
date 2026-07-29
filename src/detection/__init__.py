"""
Module detection gom các thành phần liên quan trực tiếp tới phát hiện đối tượng.

Mục tiêu của package này là tách YOLO ra khỏi runtime chính:
- Runtime chỉ gọi detector và nhận dữ liệu đã chuẩn hóa.
- Zone, tracker, ReID, UART, WebSocket không phụ thuộc trực tiếp vào object của YOLO.
"""

from typing import Any


__all__ = [
    "Detection",
    "InferenceFrame",
    "YoloDetector",
    "YoloDetectorConfig",
    "parse_yolo_result",
    "resolve_model_artifact",
    "resolve_model_path",
    "supported_models",
    "validate_model_config",
]


# ─────────────────────────────────────────────────────────────────────────────
def __getattr__(name: str) -> Any:
    """Lazy import public API để không kéo Ultralytics khi chỉ cần Detection."""
    if name in {"Detection", "InferenceFrame", "parse_yolo_result"}:
        from src.detection.datatypes import Detection, InferenceFrame
        from src.detection.utils import parse_yolo_result

        return {
            "Detection": Detection,
            "InferenceFrame": InferenceFrame,
            "parse_yolo_result": parse_yolo_result,
        }[name]

    if name in {
        "resolve_model_artifact",
        "resolve_model_path",
        "supported_models",
        "validate_model_config",
    }:
        from src.detection.model_registry import (
            resolve_model_artifact,
            resolve_model_path,
            supported_models,
            validate_model_config,
        )

        return {
            "resolve_model_artifact": resolve_model_artifact,
            "resolve_model_path": resolve_model_path,
            "supported_models": supported_models,
            "validate_model_config": validate_model_config,
        }[name]

    if name in {"YoloDetector", "YoloDetectorConfig"}:
        from src.detection.yolo_detector import YoloDetector, YoloDetectorConfig

        return {
            "YoloDetector": YoloDetector,
            "YoloDetectorConfig": YoloDetectorConfig,
        }[name]

    raise AttributeError(f"module 'src.detection' has no attribute '{name}'")
