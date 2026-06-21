"""
Vẽ bounding box người và info overlay.

Mỗi bbox có thể hiển thị: track_id, global_id, confidence, ReID status, zone.
Màu bbox thay đổi theo ReID status để dễ phân biệt trực quan.
"""

from __future__ import annotations

from typing import Optional, Sequence

import cv2
import numpy as np

from src.visualization.utils import (
    clamp,
    draw_transparent_rect,
    get_draw_scale,
    put_text,
    scale_float,
    scale_int,
)
from src.visualization.colors import bbox_color, id_color


# ─────────────────────────────────────────────────────────────────────────────
def draw_person_bbox(
    frame: np.ndarray,
    bbox: tuple[float, float, float, float],
    *,
    track_id  : Optional[int]   = None,
    confidence: Optional[float] = None,
    global_id : Optional[int]   = None,
    status    : Optional[str]   = None,
    zone_name : Optional[str]   = None,
) -> None:
    """
    Vẽ một bbox người kèm info block bán trong suốt bên trong.

    Màu viền:
    - Có global_id → màu theo id_color(global_id)
    - Không có global_id → màu theo bbox_color(status)
    """
    x1, y1, x2, y2 = (int(v) for v in bbox)
    h, w = frame.shape[:2]
    x1, y1 = clamp(x1, 0, w - 1), clamp(y1, 0, h - 1)
    x2, y2 = clamp(x2, x1 + 1, w), clamp(y2, y1 + 1, h)

    scale     = get_draw_scale(frame)
    thickness = scale_int(3, scale)
    color     = id_color(global_id) if global_id is not None else bbox_color(status)

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
    _draw_info_block(
        frame,
        x1, y1, x2, y2,
        scale=scale,
        color=color,
        track_id=track_id,
        confidence=confidence,
        global_id=global_id,
        status=status,
        zone_name=zone_name,
    )


# ─────────────────────────────────────────────────────────────────────────────
def draw_person_bboxes(
    frame     : np.ndarray,
    bboxes    : Sequence[tuple[float, float, float, float]],
    *,
    track_ids  : Optional[Sequence[Optional[int]]]   = None,
    confidences: Optional[Sequence[Optional[float]]] = None,
    global_ids : Optional[Sequence[Optional[int]]]   = None,
    statuses   : Optional[Sequence[Optional[str]]]   = None,
    zone_names : Optional[Sequence[Optional[str]]]   = None,
) -> None:
    """Vẽ toàn bộ bbox trong một frame. Các sequence phải cùng độ dài với bboxes."""
    n = len(bboxes)

    def _get(seq, i):
        return seq[i] if seq is not None and i < len(seq) else None

    for i in range(n):
        draw_person_bbox(
            frame,
            bboxes[i],
            track_id=_get(track_ids, i),
            confidence=_get(confidences, i),
            global_id=_get(global_ids, i),
            status=_get(statuses, i),
            zone_name=_get(zone_names, i),
        )


# ─────────────────────────────────────────────────────────────────────────────
def draw_detection(
    frame         : np.ndarray,
    detection,
    *,
    draw_head_kps : bool = True,
) -> None:
    """Vẽ một Detection: bbox luôn có, skeleton hoặc center dot tuỳ task."""
    draw_person_bbox(
        frame,
        detection.bbox,
        track_id  =detection.track_id,
        confidence=detection.confidence,
        global_id =detection.global_id,
        status    =detection.status,
    )
    if detection.has_pose:
        from src.visualization.pose import draw_pose
        draw_pose(frame, detection.keypoints, detection.keypoints_conf,
                  draw_head_kps=draw_head_kps)
    else:
        _draw_bbox_center(frame, detection.bbox)


def draw_detections(
    frame         : np.ndarray,
    detections    : Sequence,
    *,
    draw_head_kps : bool = True,
) -> None:
    """Vẽ toàn bộ detections trong một frame."""
    for d in detections:
        draw_detection(frame, d, draw_head_kps=draw_head_kps)


# ─────────────────────────────────────────────────────────────────────────────
def _draw_bbox_center(frame: np.ndarray, bbox: tuple) -> None:
    """Vẽ center dot của bbox — dùng cho detect task."""
    x1, y1, x2, y2 = bbox
    cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
    scale = get_draw_scale(frame)
    r = scale_int(5, scale)
    b = scale_int(2, scale)
    cv2.circle(frame, (cx, cy), r + b, (30, 30, 30), -1, cv2.LINE_AA)
    cv2.circle(frame, (cx, cy), r, (255, 255, 255), -1, cv2.LINE_AA)


# ─────────────────────────────────────────────────────────────────────────────
def _draw_info_block(
    frame    : np.ndarray,
    x1       : int,
    y1       : int,
    x2       : int,
    y2       : int,
    *,
    scale    : float,
    color    : tuple,
    track_id : Optional[int],
    confidence: Optional[float],
    global_id: Optional[int],
    status   : Optional[str],
    zone_name: Optional[str],
) -> None:
    """Vẽ info block bán trong suốt bên trong góc trên-trái của bbox."""
    rows = _build_info_rows(
        track_id=track_id,
        confidence=confidence,
        global_id=global_id,
        status=status,
        zone_name=zone_name,
    )
    if not rows:
        return

    font       = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = scale_float(0.55, scale)
    thickness  = scale_int(1, scale)
    pad_x      = scale_int(8, scale)
    pad_y      = scale_int(6, scale)
    line_gap   = scale_int(4, scale)

    (_, text_h), baseline = cv2.getTextSize("Ag", font, font_scale, thickness)
    line_h    = text_h + baseline
    block_h   = pad_y * 2 + len(rows) * line_h + (len(rows) - 1) * line_gap
    block_w   = x2 - x1
    inset     = scale_int(3, scale)
    bx1       = clamp(x1 + inset, 0, frame.shape[1] - 1)
    by1       = clamp(y1 + inset, 0, frame.shape[0] - 1)
    bx2       = clamp(bx1 + block_w - inset * 2, bx1 + 1, frame.shape[1])
    by2       = clamp(by1 + block_h, by1 + 1, frame.shape[0])

    draw_transparent_rect(frame, bx1, by1, bx2, by2, (0, 0, 0), alpha=0.45)

    text_x = bx1 + pad_x
    text_y = by1 + pad_y + text_h
    for label, value in rows:
        if text_y > by2 - pad_y:
            break
        text = f"{label}: {value}" if value is not None else label
        put_text(frame, text, (text_x, text_y), font=font, font_scale=font_scale,
                 color=(255, 255, 255), thickness=thickness)
        text_y += line_h + line_gap


# ─────────────────────────────────────────────────────────────────────────────
def _build_info_rows(
    *,
    track_id  : Optional[int],
    confidence: Optional[float],
    global_id : Optional[int],
    status    : Optional[str],
    zone_name : Optional[str],
) -> list[tuple[str, Optional[str]]]:
    rows: list[tuple[str, Optional[str]]] = []

    if track_id is not None:
        rows.append(("tid", str(track_id)))
    if global_id is not None:
        rows.append(("gid", f"{global_id:02d}"))
    if confidence is not None:
        rows.append(("cnf", f"{confidence * 100:.0f}%"))
    if status is not None:
        rows.append(("sts", status))
    if zone_name is not None:
        rows.append(("zon", zone_name))

    return rows
