"""
Wrapper YOLO cho tầng detection.

Class trong file này chỉ chịu trách nhiệm:
- Resolve và load model YOLO.
- Chạy batch inference trên list frame numpy.
- Parse result của YOLO thành `InferenceFrame`.
- Cleanup tài nguyên predictor khi runtime dừng.

Frame được cấp từ bên ngoài (MediaSources); YOLO không còn tự quản lý RTSP.

Lưu ý về tracking đa camera:
  Ultralytics model.track() với source là list numpy array (mode="image") chỉ
  tạo 1 ByteTrack instance cho toàn bộ batch, khiến các frame từ các camera
  khác nhau đi qua cùng 1 tracker — ByteTrack coi chúng là frame liên tiếp
  của cùng 1 video, gây nhầm lẫn track_id và bỏ sót detection.
  Fix: dùng predict() cho batch inference, sau đó áp dụng ByteTrack riêng
  cho từng camera index.
"""

from dataclasses import dataclass
import gc
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
from ultralytics import YOLO
from ultralytics.trackers import BYTETracker
from ultralytics.utils.checks import check_yaml
from ultralytics.utils import IterableSimpleNamespace, YAML

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
        # Tạo tất cả tracker trước khi bất kỳ frame nào được xử lý.
        # BYTETracker.__init__ gọi reset_id() làm reset BaseTrack._count (class-level).
        # Nếu tạo lazy, mỗi camera mới tạo tracker sẽ reset counter về 0 → ID restart.
        # Tạo hết upfront → reset_id() cuối cùng xảy ra trước khi ID nào được gán
        # → next_id() tăng liên tục xuyên suốt tất cả camera, giống behavior của test2.py.
        self._trackers: Dict[int, BYTETracker] = self._build_trackers(config)

    def predict_batch(self, frames: List[np.ndarray]) -> List[InferenceFrame]:
        """Chạy inference trên batch frame và trả danh sách InferenceFrame."""
        results = self.model.predict(**self._build_predict_kwargs(frames))
        return [self._parse_result(r, i) for i, r in enumerate(results)]

    def track_batch(self, frames: List[np.ndarray]) -> List[InferenceFrame]:
        """
        Chạy batch detection rồi apply ByteTrack riêng cho từng camera.

        Không dùng model.track() trực tiếp vì Ultralytics chỉ tạo 1 tracker
        cho cả batch khi source là numpy arrays (mode="image"), làm tracker
        trộn lẫn detections giữa các camera với nhau.
        """
        if len(frames) != self.config.batch_size:
            raise ValueError(
                f"track_batch nhận {len(frames)} frame nhưng cấu hình batch_size="
                f"{self.config.batch_size}; mỗi camera phải có đúng một tracker tương ứng."
            )

        results = self.model.predict(**self._build_predict_kwargs(frames))
        output = []
        for i, (result, frame) in enumerate(zip(results, frames)):
            track_id_by_index = self._apply_tracker(i, result, frame)
            output.append(self._parse_result(result, i, track_id_by_index))
        return output

    def close(self) -> None:
        """Dọn tài nguyên predictor/model nội bộ của Ultralytics."""
        try:
            model = getattr(self, "model", None)
            if model is not None:
                try:
                    model.to("cpu")
                except Exception:
                    pass

                predictor = getattr(model, "predictor", None)
                if predictor is not None:
                    model.predictor = None

                self.model = None
        except Exception:
            pass
        finally:
            self._trackers.clear()
            _release_torch_memory()

    # ── private ───────────────────────────────────────────────────────────────

    def _apply_tracker(
        self, camera_idx: int, result: Any, frame: np.ndarray
    ) -> Dict[int, int]:
        """
        Chạy ByteTrack cho một camera và trả mapping {index detection gốc → track_id}.

        Tracker CHỈ gắn track_id, không loại bỏ detection nào. ByteTrack chỉ trả
        track đã activated (người mới xuất hiện phải đợi frame sau mới được confirm),
        nên nếu lấy `result[idx]` sẽ đánh mất các detection chưa confirm. Thay vào đó
        ta giữ nguyên mọi detection; cái nào ByteTrack chưa gắn id thì track_id=None.
        """
        tracker = self._get_tracker(camera_idx)
        det = result.boxes.cpu().numpy()
        tracks = tracker.update(det, frame)
        if len(tracks) == 0:
            return {}
        # STrack.result = [x1, y1, x2, y2, track_id, score, cls, idx].
        # Cột -1 (idx) = vị trí detection gốc; cột 4 = track_id.
        return {int(track[-1]): int(track[4]) for track in tracks}

    @staticmethod
    def _build_trackers(config: "YoloDetectorConfig") -> "Dict[int, BYTETracker]":
        """Tạo N tracker đồng loạt để reset_id() cuối cùng xảy ra trước khi frame đầu tiên."""
        cfg_path = check_yaml(config.tracker)
        cfg = IterableSimpleNamespace(**YAML.load(cfg_path))
        return {i: BYTETracker(args=cfg) for i in range(config.batch_size)}

    def _get_tracker(self, camera_idx: int) -> BYTETracker:
        return self._trackers[camera_idx]

    def _parse_result(
        self,
        result: Any,
        frame_index: int,
        track_id_by_index: Optional[Dict[int, int]] = None,
    ) -> InferenceFrame:
        return InferenceFrame(
            detections  = parse_yolo_result(result, track_id_by_index),
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

    @staticmethod
    def _extract_resolution(result: Any) -> Optional[Tuple[int, int]]:
        orig_img = getattr(result, "orig_img", None)
        if orig_img is None or not hasattr(orig_img, "shape"):
            return None
        height, width = orig_img.shape[:2]
        return int(width), int(height)


def _release_torch_memory() -> None:
    gc.collect()

    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        except Exception:
            pass

    if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
        try:
            torch.mps.empty_cache()
        except Exception:
            pass
