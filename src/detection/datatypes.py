"""
Kiểu dữ liệu chuẩn cho kết quả detection / pose.

File này là lớp biên giữa Ultralytics và phần còn lại của hệ thống.
Các module phía sau (zone, ReID, visualization) chỉ đọc `Detection` hoặc
`InferenceFrame` — không phụ thuộc trực tiếp vào object của YOLO.

Hỗ trợ cả hai loại model:
  - detect : chỉ có bbox + confidence + class_id
  - pose   : thêm keypoints (17, 2) và keypoints_conf (17,)
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

import numpy as np


BBoxXYXY = Tuple[float, float, float, float]


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Detection:
    """
    Một object được phát hiện trong một frame.

    `bbox` dùng format xyxy pixel: (x1, y1, x2, y2).
    `track_id` chỉ có khi detection sinh ra từ `model.track(...)`.
    `keypoints` / `keypoints_conf` chỉ có khi chạy model pose.
    `global_id`, `similarity`, `status` được gắn vào bởi tầng ReID.
    """

    bbox      : BBoxXYXY
    confidence: float
    class_id  : Optional[int]   = None
    track_id  : Optional[int]   = None
    class_name: Optional[str]   = None

    # Pose — shape (17, 2) xy pixel và (17,) confidence mỗi keypoint.
    # Loại khỏi hash/compare vì np.ndarray không hashable.
    keypoints     : Optional[np.ndarray] = field(default=None, hash=False, compare=False)
    keypoints_conf: Optional[np.ndarray] = field(default=None, hash=False, compare=False)

    # ReID — được gắn sau bởi tầng ReID pipeline.
    global_id : Optional[int]   = None
    similarity: Optional[float] = None
    status    : Optional[str]   = None

    @property
    def has_pose(self) -> bool:
        return self.keypoints is not None

    def bbox_as_array(self) -> np.ndarray:
        """Trả bbox dạng numpy array (x1, y1, x2, y2)."""
        return np.asarray(self.bbox, dtype=np.float32)

    def bbox_normalized(self, width: int, height: int) -> List[float]:
        """Chuyển bbox sang xywh normalize — dùng cho WebSocket payload."""
        x1, y1, x2, y2 = self.bbox
        return [
            float(x1 / width),
            float(y1 / height),
            float((x2 - x1) / width),
            float((y2 - y1) / height),
        ]


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class InferenceFrame:
    """
    Kết quả inference cho một frame thuộc một camera.

    Dùng được với cả detect và pose model — detections chứa keypoints
    khi chạy pose, bỏ trống khi chạy detect thuần.
    """

    detections : List[Detection]           = field(default_factory=list)
    resolution : Optional[Tuple[int, int]] = None   # (width, height)
    frame_index: Optional[int]             = None
    camera_id  : Optional[str]             = None
    raw_result : Optional[Any]             = None   # YOLO result gốc, chỉ dùng để debug

    @property
    def count(self) -> int:
        return len(self.detections)

    @property
    def tracked_count(self) -> int:
        return sum(1 for d in self.detections if d.track_id is not None)

    @property
    def pose_count(self) -> int:
        return sum(1 for d in self.detections if d.has_pose)