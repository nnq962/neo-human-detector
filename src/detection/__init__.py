"""
Module detection gom các thành phần liên quan trực tiếp tới phát hiện đối tượng.

Mục tiêu của package này là tách YOLO ra khỏi runtime chính:
- Runtime chỉ gọi detector và nhận dữ liệu đã chuẩn hóa.
- Zone, tracker, ReID, UART, WebSocket không phụ thuộc trực tiếp vào object của YOLO.
"""

from src.detection.detections import Detection, DetectionFrame, parse_yolo_boxes
from src.detection.model_registry import (
    MODEL_PATHS,
    resolve_model_path,
    supported_model_configs,
    validate_model_config,
)
from src.detection.yolo_detector import (
    YoloDetector,
    YoloDetectorConfig,
    build_yolo_detector_config,
)

__all__ = [
    "Detection",
    "DetectionFrame",
    "MODEL_PATHS",
    "YoloDetector",
    "YoloDetectorConfig",
    "build_yolo_detector_config",
    "parse_yolo_boxes",
    "resolve_model_path",
    "supported_model_configs",
    "validate_model_config",
]
