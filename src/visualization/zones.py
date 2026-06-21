"""
Vẽ zone polygon với màu theo trạng thái ZoneState.
"""

from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np

from src.visualization.utils import get_draw_scale, put_text, scale_float, scale_int
from src.visualization.colors import (
    ZONE_EMPTY,
    ZONE_FALLBACK,
    ZONE_OCCUPIED,
    ZONE_PENDING_ENTER,
    ZONE_PENDING_EXIT,
)


# Import lazy để tránh circular import khi zones.models import colors sau này.
def _zone_color(zone) -> tuple:
    from src.zones_management.datatypes import ZoneState

    mapping = {
        ZoneState.EMPTY        : ZONE_EMPTY,
        ZoneState.PENDING_ENTER: ZONE_PENDING_ENTER,
        ZoneState.OCCUPIED     : ZONE_OCCUPIED,
        ZoneState.PENDING_EXIT : ZONE_PENDING_EXIT,
    }
    return mapping.get(zone.state, ZONE_FALLBACK)


# ─────────────────────────────────────────────────────────────────────────────
def draw_zone(frame: np.ndarray, zone) -> None:
    """Vẽ một zone: polygon fill bán trong suốt + viền + nhãn trạng thái."""
    pts   = zone.pts
    color = _zone_color(zone)
    scale = get_draw_scale(frame)
    border_thickness = max(1, scale_int(3, scale) // 2)

    overlay = frame.copy()
    cv2.fillPoly(overlay, [pts], color=color)
    cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)

    cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=border_thickness)

    _draw_zone_label(frame, zone, color, scale)


# ─────────────────────────────────────────────────────────────────────────────
def draw_zones(frame: np.ndarray, zones: Sequence) -> None:
    """Vẽ tất cả zone lên frame."""
    for zone in zones:
        draw_zone(frame, zone)


# ─────────────────────────────────────────────────────────────────────────────
def _draw_zone_label(frame: np.ndarray, zone, color: tuple, scale: float) -> None:
    """Vẽ nhãn tên zone + state ở tâm polygon."""
    pts      = zone.pts
    center_x = int(pts[:, 0].mean())
    center_y = int(pts[:, 1].mean())
    label    = f"{zone.name} [{zone.state.value}]"

    put_text(
        frame,
        label,
        (center_x, center_y),
        font=cv2.FONT_HERSHEY_DUPLEX,
        font_scale=scale_float(0.75, scale),
        color=color,
        thickness=scale_int(2, scale),
    )
