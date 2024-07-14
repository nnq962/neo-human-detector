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
    if not np.isfinite([x1, y1, x2, y2]).all():
        return False

    if mode == "center":
        point = (int((x1 + x2) // 2), int((y1 + y2) // 2))
    else:
        point = (int((x1 + x2) // 2), int(y2))

    # measureDist=False để tăng tốc độ (chỉ cần biết trong/ngoài, không cần khoảng cách)
    result = cv2.pointPolygonTest(points, point, measureDist=False)

    return result >= 0


def assign_bboxes_to_zones(
    bboxes: np.ndarray,
    zones: List[Zone],
    zone_check_mode: str,
) -> Tuple[List[Optional[str]], Dict[str, int]]: # Đổi type hint từ bool sang int
    """
    Gắn từng bbox vào zone tương ứng và đếm số lượng bbox trong mỗi zone.
    """
    # Tạo list để lưu tên zone cho mỗi bbox, khởi tạo với None (chưa gắn zone nào): [None, None, ...]
    zone_names: List[Optional[str]] = [None] * len(bboxes)
    
    # Khởi tạo bộ đếm 0 cho tất cả các zone thay vì False: {'zone1': 0, 'zone2': 0, ...}
    zone_counts = {zone.key: 0 for zone in zones}

    for i, bbox in enumerate(bboxes):
        for zone in zones:
            if is_bbox_in_zone(bbox, zone.pts, mode=zone_check_mode):
                zone_names[i] = zone.name
                
                # Tăng bộ đếm lên 1 khi phát hiện có người
                zone_counts[zone.key] += 1 
                
                # Vẫn giữ break (mỗi người chỉ đếm cho 1 zone đầu tiên lọt vào)
                break
    
    # zone_names: ['zone1', 'zone2', None, 'zone1', ...]
    # zone_counts: {'zone1': 2, 'zone2': 1, ...}
    return zone_names, zone_counts
