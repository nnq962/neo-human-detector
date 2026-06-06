"""
Kiểu dữ liệu chuẩn cho kết quả phát hiện đối tượng.

File này là lớp biên giữa thư viện YOLO/Ultralytics và phần còn lại của hệ thống.
Các module phía sau như zone, tracking, ReID chỉ nên đọc `Detection` hoặc
`DetectionFrame`, thay vì đọc trực tiếp `result.boxes` của YOLO.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


BBoxXYXY = Tuple[float, float, float, float]


# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class Detection:
    """
    Một object được phát hiện trong một frame.

    `bbox` dùng format xyxy theo pixel gốc: (x1, y1, x2, y2).
    `class_id` có thể None vì một số model head custom không cần class rõ ràng.
    `track_id` chỉ có khi detection được sinh ra từ `model.track(...)`.
    """

    bbox: BBoxXYXY
    confidence: float
    class_id: Optional[int] = None
    track_id: Optional[int] = None
    label: Optional[str] = None

    def to_xywh_normalized(self, width: int, height: int) -> List[float]:
        """Chuyển bbox xyxy pixel sang xywh normalize để gửi WebSocket."""
        x1, y1, x2, y2 = self.bbox

        return [
            float(x1 / width),
            float(y1 / height),
            float((x2 - x1) / width),
            float((y2 - y1) / height),
        ]

    def as_xyxy_array(self) -> np.ndarray:
        """Trả bbox dạng numpy array để tái sử dụng với các hàm hình học hiện tại."""
        return np.asarray(self.bbox, dtype=np.float32)


# -----------------------------------------------------------------------------
@dataclass
class DetectionFrame:
    """
    Kết quả phát hiện cho một frame thuộc một camera.

    `raw_result` được giữ lại tạm thời để debug hoặc phục vụ bước migration.
    Khi pipeline mới ổn định, runtime có thể bỏ phụ thuộc vào field này.
    """

    detections: List[Detection] = field(default_factory=list)
    resolution: Optional[Tuple[int, int]] = None
    frame_index: Optional[int] = None
    camera_id: Optional[str] = None
    raw_result: Optional[Any] = None

    @property
    def count(self) -> int:
        """Số detection hợp lệ trong frame."""
        return len(self.detections)

    def bboxes_array(self) -> np.ndarray:
        """Trả toàn bộ bbox dạng ndarray shape (N, 4), tương thích code zone cũ."""
        if not self.detections:
            return np.empty((0, 4), dtype=np.float32)

        return np.asarray([item.bbox for item in self.detections], dtype=np.float32)

    def confidences_array(self) -> np.ndarray:
        """Trả toàn bộ confidence dạng ndarray shape (N,), tương thích code cũ."""
        if not self.detections:
            return np.empty((0,), dtype=np.float32)

        return np.asarray([item.confidence for item in self.detections], dtype=np.float32)


# -----------------------------------------------------------------------------
def parse_yolo_boxes(boxes: Any) -> List[Detection]:
    """
    Parse `result.boxes` của YOLO thành danh sách `Detection`.

    Logic ở đây cố ý phòng thủ:
    - Nếu YOLO trả bbox rỗng thì trả list rỗng.
    - Nếu bbox/confidence có NaN hoặc inf thì bỏ qua detection đó.
    - Nếu có class id thì giữ lại để tracking/ReID có thể dùng về sau.
    """
    if boxes is None or len(boxes) == 0:
        return []

    bboxes = boxes.xyxy.cpu().numpy()
    confs = boxes.conf.cpu().numpy()
    class_ids = _extract_class_ids(boxes, len(bboxes))
    track_ids = _extract_track_ids(boxes, len(bboxes))

    detections: List[Detection] = []
    for bbox, confidence, class_id, track_id in zip(bboxes, confs, class_ids, track_ids):
        if not _is_valid_detection(bbox, confidence):
            continue

        x1, y1, x2, y2 = bbox[:4]
        detections.append(
            Detection(
                bbox=(float(x1), float(y1), float(x2), float(y2)),
                confidence=float(confidence),
                class_id=class_id,
                track_id=track_id,
            )
        )

    return detections


# -----------------------------------------------------------------------------
def detections_to_websocket_objects(
    detections: List[Detection],
    resolution: Tuple[int, int],
) -> List[Dict[str, Any]]:
    """Đóng gói detection thành object nhỏ cho WebSocket preview."""
    width, height = resolution

    return [
        {
            "bbox": detection.to_xywh_normalized(width, height),
            "conf": detection.confidence,
        }
        for detection in detections
    ]


# -----------------------------------------------------------------------------
def _extract_class_ids(boxes: Any, count: int) -> List[Optional[int]]:
    """Lấy class id từ YOLO boxes nếu tồn tại."""
    if not hasattr(boxes, "cls") or boxes.cls is None:
        return [None] * count

    raw_class_ids = boxes.cls.cpu().numpy()
    class_ids: List[Optional[int]] = []

    for value in raw_class_ids:
        class_ids.append(int(value) if np.isfinite(value) else None)

    if len(class_ids) < count:
        class_ids.extend([None] * (count - len(class_ids)))

    return class_ids[:count]


# -----------------------------------------------------------------------------
def _extract_track_ids(boxes: Any, count: int) -> List[Optional[int]]:
    """Lấy ByteTrack id từ YOLO tracking result nếu tồn tại."""
    if not hasattr(boxes, "id") or boxes.id is None:
        return [None] * count

    raw_track_ids = boxes.id.cpu().numpy()
    track_ids: List[Optional[int]] = []

    for value in raw_track_ids:
        track_ids.append(int(value) if np.isfinite(value) else None)

    if len(track_ids) < count:
        track_ids.extend([None] * (count - len(track_ids)))

    return track_ids[:count]


# -----------------------------------------------------------------------------
def _is_valid_detection(bbox: np.ndarray, confidence: float) -> bool:
    """Kiểm tra detection có tọa độ và confidence hợp lệ hay không."""
    if not np.isfinite(bbox[:4]).all() or not np.isfinite(confidence):
        return False

    x1, y1, x2, y2 = bbox[:4]
    return x2 > x1 and y2 > y1
