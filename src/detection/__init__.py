"""
Module detection gom các thành phần liên quan trực tiếp tới phát hiện đối tượng.

Mục tiêu của package này là tách YOLO ra khỏi runtime chính:
- Runtime chỉ gọi detector và nhận dữ liệu đã chuẩn hóa.
- Zone, tracker, ReID, UART, WebSocket không phụ thuộc trực tiếp vào object của YOLO.
"""

from typing import Any


__all__ = [
    "Detection",
    "DetectionFrame",
    "MODEL_PATHS",
    "YoloDetector",
    "YoloDetectorConfig",
    "parse_yolo_boxes",
    "resolve_model_path",
    "supported_model_configs",
    "validate_model_config",
]


# ─────────────────────────────────────────────────────────────────────────────
def __getattr__(name: str) -> Any:
    """Lazy import public API để không kéo Ultralytics khi chỉ cần Detection."""
    if name in {"Detection", "DetectionFrame", "parse_yolo_boxes"}:
        from src.detection.detections import Detection, DetectionFrame, parse_yolo_boxes

        return {
            "Detection": Detection,
            "DetectionFrame": DetectionFrame,
            "parse_yolo_boxes": parse_yolo_boxes,
        }[name]

    if name in {
        "MODEL_PATHS",
        "resolve_model_path",
        "supported_model_configs",
        "validate_model_config",
    }:
        from src.detection.model_registry import (
            MODEL_PATHS,
            resolve_model_path,
            supported_model_configs,
            validate_model_config,
        )

        return {
            "MODEL_PATHS": MODEL_PATHS,
            "resolve_model_path": resolve_model_path,
            "supported_model_configs": supported_model_configs,
            "validate_model_config": validate_model_config,
        }[name]

    if name in {"YoloDetector", "YoloDetectorConfig"}:
        from src.detection.yolo_detector import YoloDetector, YoloDetectorConfig

        return {
            "YoloDetector": YoloDetector,
            "YoloDetectorConfig": YoloDetectorConfig,
        }[name]

    raise AttributeError(f"module 'src.detection' has no attribute '{name}'")
