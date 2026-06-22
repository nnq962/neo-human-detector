
from typing import Any, Dict, List, Optional, Tuple
from src.detection.datatypes import Detection
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
def parse_yolo_result(
    result: Any,
    track_id_by_index: Optional[Dict[int, int]] = None,
) -> List[Detection]:
    """
    Parse một YOLO result thành danh sách Detection.

    Hoạt động với cả detect model (result.boxes) và pose model
    (result.boxes + result.keypoints). Phòng thủ: NaN/inf bị loại,
    bbox rỗng trả list rỗng.

    `track_id_by_index` (nếu có) là mapping {index detection gốc → track_id} do
    tracker bên ngoài cung cấp. Detection nào không có trong mapping vẫn được giữ
    với track_id=None — tracker không được làm mất detection.
    """
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return []

    bboxes    = boxes.xyxy.cpu().numpy()
    confs     = boxes.conf.cpu().numpy()
    class_ids = _extract_class_ids(boxes, len(bboxes))
    track_ids = _extract_track_ids(boxes, len(bboxes))
    kps_xy, kps_conf = _extract_keypoints(result, len(bboxes))

    detections: List[Detection] = []
    for i, (bbox, conf, class_id, track_id) in enumerate(
        zip(bboxes, confs, class_ids, track_ids)
    ):
        if not _is_valid_detection(bbox, conf):
            continue

        if track_id_by_index is not None:
            track_id = track_id_by_index.get(i)

        x1, y1, x2, y2 = bbox[:4]
        detections.append(
            Detection(
                bbox           = (float(x1), float(y1), float(x2), float(y2)),
                confidence     = float(conf),
                class_id       = class_id,
                track_id       = track_id,
                keypoints      = kps_xy[i]   if kps_xy   is not None else None,
                keypoints_conf = kps_conf[i] if kps_conf is not None else None,
            )
        )

    return detections


# ─────────────────────────────────────────────────────────────────────────────
def _extract_class_ids(boxes: Any, count: int) -> List[Optional[int]]:
    if not hasattr(boxes, "cls") or boxes.cls is None:
        return [None] * count
    raw = boxes.cls.cpu().numpy()
    ids: List[Optional[int]] = [int(v) if np.isfinite(v) else None for v in raw]
    if len(ids) < count:
        ids.extend([None] * (count - len(ids)))
    return ids[:count]


# ─────────────────────────────────────────────────────────────────────────────
def _extract_track_ids(boxes: Any, count: int) -> List[Optional[int]]:
    if not hasattr(boxes, "id") or boxes.id is None:
        return [None] * count
    raw = boxes.id.cpu().numpy()
    ids: List[Optional[int]] = [int(v) if np.isfinite(v) else None for v in raw]
    if len(ids) < count:
        ids.extend([None] * (count - len(ids)))
    return ids[:count]


# ─────────────────────────────────────────────────────────────────────────────
def _extract_keypoints(
    result: Any, count: int
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """Lấy keypoints từ YOLO pose result. Trả (None, None) nếu là detect model."""
    kp_data = getattr(result, "keypoints", None)
    if kp_data is None:
        return None, None
    try:
        xy   = kp_data.xy.cpu().numpy()    # (N, 17, 2)
        conf = kp_data.conf.cpu().numpy()  # (N, 17)
        return xy, conf
    except Exception:
        return None, None


# ─────────────────────────────────────────────────────────────────────────────
def _is_valid_detection(bbox: np.ndarray, confidence: float) -> bool:
    if not np.isfinite(bbox[:4]).all() or not np.isfinite(confidence):
        return False
    x1, y1, x2, y2 = bbox[:4]
    return x2 > x1 and y2 > y1
