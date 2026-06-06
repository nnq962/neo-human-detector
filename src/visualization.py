import cv2
from typing import List, Optional
import numpy as np
from src.models import Zone


COLOR_BBOX_NORMAL = (255, 0, 0)    # xanh dương: bbox ngoài zone
COLOR_BBOX_IN_ZONE = (0, 200, 0)   # xanh lá: bbox trong zone


def draw_zones(frame: np.ndarray, zones: List[Zone]) -> np.ndarray:
    """Vẽ lớp phủ các vùng lên khung hình."""
    overlay = frame.copy()

    for zone in zones:
        pts = zone.pts
        color = zone.get_current_color()

        cv2.fillPoly(overlay, [pts], color=color)
        cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)

        label = f"{zone.name} [{zone.state.value}]"
        cx = int(pts[:, 0].mean())
        cy = int(pts[:, 1].mean())
        cv2.putText(frame, label, (cx, cy), cv2.FONT_HERSHEY_DUPLEX, 0.8, color, 2)

    cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
    return frame


def draw_overlay(
    frame: np.ndarray,
    bboxes: np.ndarray,
    confs: np.ndarray,
    zone_names: List[Optional[str]],
) -> np.ndarray:
    """Vẽ bbox, confidence và tên zone nếu bbox thuộc vùng giám sát."""
    for bbox, conf, zone_name in zip(bboxes, confs, zone_names):
        if not np.isfinite(bbox[:4]).all() or not np.isfinite(conf):
            continue

        x1, y1, x2, y2 = map(int, bbox[:4])
        in_zone = zone_name is not None
        color = COLOR_BBOX_IN_ZONE if in_zone else COLOR_BBOX_NORMAL

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness=2)

        if in_zone:
            label = f"[{conf:.2f}] [{zone_name}]"
        else:
            label = f"[{conf:.2f}]"

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_DUPLEX, 0.55, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
        cv2.putText(
            frame,
            label,
            (x1 + 2, y1 - 4),
            cv2.FONT_HERSHEY_DUPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    return frame
