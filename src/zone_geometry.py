import aidcv as cv2
from typing import Dict, List, Optional, Tuple
import numpy as np
from src.models import Zone


def is_bbox_in_zone(
    bbox: tuple,
    points: np.ndarray,
    mode: str = "center",
) -> bool:
    """
    Kiểm tra một bounding box có nằm trong vùng đa giác zone hay không.

    Args:
        bbox (tuple/np.ndarray): Tọa độ khung nhận diện (x1, y1, x2, y2).
        points (np.ndarray): Mảng các đỉnh của đa giác zone (N, 2).
        mode (str): Chế độ kiểm tra:
            - 'center': Dựa trên điểm tâm khung.
            - 'bottom_center': Dựa trên điểm giữa cạnh dưới.

    Returns:
        bool: True nếu điểm đại diện nằm trong hoặc trên cạnh zone.
    """
    if mode not in ("center", "bottom_center"):
        raise ValueError(
            f"mode phải là 'center' hoặc 'bottom_center', nhận được: '{mode}'"
        )

    x1, y1, x2, y2 = bbox[:4]

    if mode == "center":
        point = (int((x1 + x2) / 2), int((y1 + y2) / 2))
    else:
        point = (int((x1 + x2) / 2), int(y2))

    result = cv2.pointPolygonTest(points, point, measureDist=False)
    return result >= 0


def assign_bboxes_to_zones(
    bboxes: np.ndarray,
    zones: List[Zone],
    zone_check_mode: str,
) -> Tuple[List[Optional[str]], Dict[str, bool]]:
    """
    Gắn từng bbox vào zone tương ứng và đánh dấu zone nào có bbox trong frame hiện tại.
    """
    zone_names: List[Optional[str]] = [None] * len(bboxes)
    zone_has_detection = {zone.name: False for zone in zones}

    if len(bboxes) > 0:
        for i, bbox in enumerate(bboxes):
            for zone in zones:
                if is_bbox_in_zone(bbox, zone.pts, mode=zone_check_mode):
                    zone_names[i] = zone.name
                    zone_has_detection[zone.name] = True
                    break

    return zone_names, zone_has_detection
