"""
Wrapper YOLO cho tầng detection.

Class trong file này chỉ chịu trách nhiệm:
- Resolve và load model YOLO.
- Chạy batch inference trên list frame numpy.
- Parse result của YOLO thành `InferenceFrame`.
- Cleanup tài nguyên predictor khi runtime dừng.

Frame được cấp từ bên ngoài (MediaSources); YOLO không còn tự quản lý RTSP.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from ultralytics import YOLO

from src.detection.datatypes import InferenceFrame
from src.detection.utils import parse_yolo_result
from src.detection.model_registry import resolve_model_path


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class YoloDetectorConfig:
    """Cấu hình tối thiểu để chạy YOLO detection hoặc pose."""

    task       : str   = "pose"            # "detect" hoặc "pose"
    model_size : str   = "nano"
    batch_size : int   = 1
    conf       : float = 0.5
    tracker    : str   = "bytetrack.yaml"
    persist    : bool  = True
    verbose    : bool  = False


# ─────────────────────────────────────────────────────────────────────────────
class YoloDetector:
    """
    Adapter mỏng bao quanh Ultralytics YOLO.

    Nhận `list[np.ndarray]` (BGR frames) từ bên ngoài và trả `list[InferenceFrame]`.
    Không tự quản lý RTSP hay stream file.
    """

    def __init__(self, config: YoloDetectorConfig):
        self.config = config
        self.model_path = resolve_model_path(config.model_size, config.task, config.batch_size)
        self.model = YOLO(self.model_path)

    def predict_batch(self, frames: List[np.ndarray]) -> List[InferenceFrame]:
        """Chạy inference trên batch frame và trả danh sách InferenceFrame."""
        results = self.model.predict(**self._build_predict_kwargs(frames))
        return [self._parse_result(r, i) for i, r in enumerate(results)]

    def track_batch(self, frames: List[np.ndarray]) -> List[InferenceFrame]:
        """Chạy YOLO tracking (ByteTrack) trên batch frame."""
        results = self.model.track(**self._build_track_kwargs(frames))
        return [self._parse_result(r, i) for i, r in enumerate(results)]

    def close(self) -> None:
        """Dọn tài nguyên predictor nội bộ của Ultralytics."""
        predictor = getattr(self.model, "predictor", None)
        if predictor is None:
            return
        try:
            self.model.predictor = None
        except Exception:
            pass

    # ── private ───────────────────────────────────────────────────────────────

    def _parse_result(self, result: Any, frame_index: int) -> InferenceFrame:
        return InferenceFrame(
            detections  = parse_yolo_result(result),
            resolution  = self._extract_resolution(result),
            frame_index = frame_index,
            raw_result  = result,
        )

    def _build_predict_kwargs(self, frames: List[np.ndarray]) -> Dict[str, Any]:
        return {
            "source" : frames,
            "conf"   : self.config.conf,
            "show"   : False,
            "stream" : False,
            "verbose": False,
            "classes": [0],
        }

    def _build_track_kwargs(self, frames: List[np.ndarray]) -> Dict[str, Any]:
        kwargs = self._build_predict_kwargs(frames)
        kwargs["tracker"] = self.config.tracker
        kwargs["persist"] = self.config.persist
        return kwargs

    @staticmethod
    def _extract_resolution(result: Any) -> Optional[Tuple[int, int]]:
        orig_img = getattr(result, "orig_img", None)
        if orig_img is None or not hasattr(orig_img, "shape"):
            return None
        height, width = orig_img.shape[:2]
        return int(width), int(height)
