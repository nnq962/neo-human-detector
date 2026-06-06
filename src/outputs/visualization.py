"""
Visualization/debug overlay bằng OpenCV.

Các hàm trong file này chỉ dùng để vẽ preview debug. Pipeline sản phẩm vẫn nên
truyền dữ liệu qua WebSocket/UART thay vì phụ thuộc vào frame đã vẽ.
"""

from typing import List, Optional, Sequence

import cv2
import numpy as np

from src.detection.detections import Detection
from src.models import Zone


COLOR_BBOX_NORMAL = (255, 0, 0)    # Xanh dương: bbox ngoài zone.
COLOR_BBOX_IN_ZONE = (0, 200, 0)   # Xanh lá: bbox nằm trong zone.
COLOR_TRACK_TEXT = (255, 255, 255)


# -----------------------------------------------------------------------------
def draw_zones(frame: np.ndarray, zones: Sequence[Zone]) -> np.ndarray:
    """Vẽ lớp phủ polygon zone và trạng thái hiện tại lên frame."""
    overlay = frame.copy()

    for zone in zones:
        points = zone.pts
        color = zone.get_current_color()

        cv2.fillPoly(overlay, [points], color=color)
        cv2.polylines(frame, [points], isClosed=True, color=color, thickness=2)
        _draw_zone_label(frame, zone, color)

    cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
    return frame


# -----------------------------------------------------------------------------
def draw_detection_overlay(
    frame: np.ndarray,
    detections: Sequence[Detection],
    zone_names: Sequence[Optional[str]],
) -> np.ndarray:
    """Vẽ bbox Detection chuẩn, confidence, zone name và track id nếu có."""
    for detection, zone_name in zip(detections, zone_names):
        x1, y1, x2, y2 = map(int, detection.bbox)
        in_zone = zone_name is not None
        color = COLOR_BBOX_IN_ZONE if in_zone else COLOR_BBOX_NORMAL
        label = _build_detection_label(detection, zone_name)

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness=2)
        _draw_detection_label(frame, label, x1, y1, color)

    return frame


# -----------------------------------------------------------------------------
def draw_legacy_overlay(
    frame: np.ndarray,
    bboxes: np.ndarray,
    confs: np.ndarray,
    zone_names: List[Optional[str]],
) -> np.ndarray:
    """
    Adapter tạm cho pipeline cũ đang dùng numpy `bboxes/confs`.

    Hàm này giữ hành vi gần giống `src/visualization.py::draw_overlay`.
    """
    detections = []
    for bbox, conf in zip(bboxes, confs):
        if not np.isfinite(bbox[:4]).all() or not np.isfinite(conf):
            continue

        x1, y1, x2, y2 = bbox[:4]
        detections.append(
            Detection(
                bbox=(float(x1), float(y1), float(x2), float(y2)),
                confidence=float(conf),
            )
        )

    return draw_detection_overlay(frame, detections, zone_names)


# -----------------------------------------------------------------------------
def _draw_zone_label(frame: np.ndarray, zone: Zone, color: tuple) -> None:
    """Vẽ nhãn tên zone ở tâm polygon."""
    points = zone.pts
    label = f"{zone.name} [{zone.state.value}]"
    center_x = int(points[:, 0].mean())
    center_y = int(points[:, 1].mean())

    cv2.putText(
        frame,
        label,
        (center_x, center_y),
        cv2.FONT_HERSHEY_DUPLEX,
        0.8,
        color,
        2,
    )


# -----------------------------------------------------------------------------
def _draw_detection_label(
    frame: np.ndarray,
    label: str,
    x: int,
    y: int,
    color: tuple,
) -> None:
    """Vẽ nền và text label cho một bbox."""
    (text_width, text_height), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_DUPLEX, 0.55, 1)
    label_y = max(y - text_height - 8, 0)

    cv2.rectangle(frame, (x, label_y), (x + text_width + 4, label_y + text_height + 8), color, -1)
    cv2.putText(
        frame,
        label,
        (x + 2, label_y + text_height + 4),
        cv2.FONT_HERSHEY_DUPLEX,
        0.55,
        COLOR_TRACK_TEXT,
        1,
        cv2.LINE_AA,
    )


# -----------------------------------------------------------------------------
def _build_detection_label(detection: Detection, zone_name: Optional[str]) -> str:
    """Tạo text label ngắn cho bbox."""
    parts = [f"{detection.confidence:.2f}"]

    if detection.track_id is not None:
        parts.append(f"id:{detection.track_id}")

    if zone_name is not None:
        parts.append(zone_name)

    return "[" + "] [".join(parts) + "]"
