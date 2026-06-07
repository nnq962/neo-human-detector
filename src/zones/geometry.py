"""
Hình học zone cho pipeline detection.

File này chỉ chịu trách nhiệm kiểm tra bbox nằm trong polygon nào và trả về
mapping đơn giản để state machine xử lý tiếp.
"""

from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from src.detection.detections import Detection
from src.zones.models import Zone


ZoneCheckMode = str


# ─────────────────────────────────────────────────────────────────────────────
def is_bbox_in_zone(
    bbox: Sequence[float],
    points: np.ndarray,
    mode: ZoneCheckMode = "center",
) -> bool:
    """
    Kiểm tra bbox có nằm trong polygon zone hay không.

    `center` dùng tâm bbox, còn `bottom_center` dùng điểm giữa cạnh dưới. Với
    bài toán người đứng/ngồi, `bottom_center` thường ổn khi cần neo theo chân.
    """
    if mode not in ("center", "bottom_center"):
        raise ValueError(
            f"zone_check_mode phải là 'center' hoặc 'bottom_center', nhận được: '{mode}'"
        )

    x1, y1, x2, y2 = bbox[:4]
    if not np.isfinite([x1, y1, x2, y2]).all():
        return False

    if mode == "center":
        point = (int((x1 + x2) // 2), int((y1 + y2) // 2))
    else:
        point = (int((x1 + x2) // 2), int(y2))

    # measureDist=False vì chỉ cần biết điểm trong/ngoài polygon.
    return cv2.pointPolygonTest(points, point, measureDist=False) >= 0


# ─────────────────────────────────────────────────────────────────────────────
def assign_detections_to_zones(
    detections: Sequence[Detection],
    zones: Sequence[Zone],
    zone_check_mode: ZoneCheckMode,
) -> Tuple[List[Optional[str]], Dict[str, int]]:
    """
    Gắn từng Detection vào zone đầu tiên chứa bbox và đếm số người trong zone.

    Returns:
        Tuple gồm:
        - zone_names: list cùng thứ tự với detections, mỗi item là tên zone hoặc None.
        - zone_counts: mapping zone.key -> số detection nằm trong zone.
    """
    zone_names: List[Optional[str]] = [None] * len(detections)
    zone_counts = {zone.key: 0 for zone in zones}

    for index, detection in enumerate(detections):
        for zone in zones:
            if is_bbox_in_zone(detection.bbox, zone.pts, mode=zone_check_mode):
                zone_names[index] = zone.name
                zone_counts[zone.key] += 1
                break

    return zone_names, zone_counts


# ─────────────────────────────────────────────────────────────────────────────
def assign_bboxes_to_zones(
    bboxes: np.ndarray,
    zones: Sequence[Zone],
    zone_check_mode: ZoneCheckMode,
) -> Tuple[List[Optional[str]], Dict[str, int]]:
    """
    Adapter tương thích cho code còn dùng ndarray bbox cũ.

    Runtime mới nên ưu tiên `assign_detections_to_zones`.
    """
    zone_names: List[Optional[str]] = [None] * len(bboxes)
    zone_counts = {zone.key: 0 for zone in zones}

    for index, bbox in enumerate(bboxes):
        for zone in zones:
            if is_bbox_in_zone(bbox, zone.pts, mode=zone_check_mode):
                zone_names[index] = zone.name
                zone_counts[zone.key] += 1
                break

    return zone_names, zone_counts
