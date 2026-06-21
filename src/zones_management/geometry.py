"""
Hình học zone cho pipeline detection / pose.

Chịu trách nhiệm duy nhất: tính điểm kiểm tra của mỗi Detection rồi xét
điểm đó có nằm trong polygon zone không.

Chiến lược chọn điểm kiểm tra theo task:
  - "detect" : tâm bbox  (x_center, y_center)
  - "pose"   : hip center (trung điểm left_hip + right_hip)
               → fallback left_hip hoặc right_hip nếu một bên không rõ
               → fallback tâm bbox nếu cả hai hip đều không rõ
"""

from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from src.detection.datatypes import Detection
from src.zones_management.datatypes import Zone


# Ngưỡng confidence tối thiểu để coi một keypoint là hợp lệ.
_KP_CONF_THRESHOLD = 0.3

# COCO indices
_L_HIP = 11
_R_HIP = 12


# ─────────────────────────────────────────────────────────────────────────────
def assign_detections_to_zones(
    detections : Sequence[Detection],
    zones      : Sequence[Zone],
    task       : str,
) -> Tuple[List[Optional[str]], Dict[str, int]]:
    """
    Gắn từng Detection vào zone đầu tiên chứa điểm kiểm tra của nó.

    Args:
        detections: danh sách Detection trong một frame.
        zones:      danh sách Zone của camera.
        task:       "detect" hoặc "pose" — quyết định cách tính điểm kiểm tra.

    Returns:
        (zone_names, zone_counts):
        - zone_names : list cùng thứ tự với detections, None nếu ngoài mọi zone.
        - zone_counts: mapping zone.key → số detection trong zone.
    """
    zone_names: List[Optional[str]] = [None] * len(detections)
    zone_counts = {zone.key: 0 for zone in zones}

    for idx, detection in enumerate(detections):
        point = _get_check_point(detection, task)
        if point is None:
            continue
        for zone in zones:
            if _is_point_in_zone(point, zone.pts):
                zone_names[idx] = zone.name
                zone_counts[zone.key] += 1
                break

    return zone_names, zone_counts


# ─────────────────────────────────────────────────────────────────────────────
def is_point_in_zone(point: Tuple[int, int], zone_pts: np.ndarray) -> bool:
    """Kiểm tra một điểm pixel có nằm trong polygon zone không."""
    return _is_point_in_zone(point, zone_pts)


# ─────────────────────────────────────────────────────────────────────────────
def _is_point_in_zone(point: Tuple[int, int], zone_pts: np.ndarray) -> bool:
    # measureDist=False: chỉ cần in/out, không cần khoảng cách.
    return cv2.pointPolygonTest(zone_pts, point, measureDist=False) >= 0


# ─────────────────────────────────────────────────────────────────────────────
def _get_check_point(
    detection: Detection,
    task: str,
) -> Optional[Tuple[int, int]]:
    """Tính điểm kiểm tra zone từ Detection theo task."""
    if task == "pose" and detection.has_pose:
        pt = _hip_point(detection.keypoints, detection.keypoints_conf)
        if pt is not None:
            return pt
        # Fallback về tâm bbox khi cả 2 hip đều không rõ
    return _bbox_center(detection.bbox)


# ─────────────────────────────────────────────────────────────────────────────
def _hip_point(
    kps  : np.ndarray,
    confs: np.ndarray,
) -> Optional[Tuple[int, int]]:
    """
    Trả điểm hip theo thứ tự ưu tiên:
      1. Trung điểm left_hip + right_hip (cả hai rõ)
      2. left_hip (chỉ trái rõ)
      3. right_hip (chỉ phải rõ)
      4. None (cả hai không rõ → caller fallback sang bbox center)
    """
    l_ok = confs[_L_HIP] >= _KP_CONF_THRESHOLD
    r_ok = confs[_R_HIP] >= _KP_CONF_THRESHOLD

    if l_ok and r_ok:
        return (
            int((kps[_L_HIP, 0] + kps[_R_HIP, 0]) / 2),
            int((kps[_L_HIP, 1] + kps[_R_HIP, 1]) / 2),
        )
    if l_ok:
        return (int(kps[_L_HIP, 0]), int(kps[_L_HIP, 1]))
    if r_ok:
        return (int(kps[_R_HIP, 0]), int(kps[_R_HIP, 1]))
    return None


# ─────────────────────────────────────────────────────────────────────────────
def _bbox_center(bbox: Sequence[float]) -> Optional[Tuple[int, int]]:
    x1, y1, x2, y2 = bbox[:4]
    if not np.isfinite([x1, y1, x2, y2]).all():
        return None
    return (int((x1 + x2) / 2), int((y1 + y2) / 2))
