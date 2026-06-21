"""
Tiện ích vẽ nội bộ dùng chung trong toàn module visualization.
"""

from __future__ import annotations

import cv2
import numpy as np


_BASE_HEIGHT = 1080


# ─────────────────────────────────────────────────────────────────────────────
def get_draw_scale(frame: np.ndarray) -> float:
    """Scale vẽ tuyến tính theo chiều cao frame, lấy Full HD làm mốc 1.0."""
    return float(np.clip(frame.shape[0] / _BASE_HEIGHT, 0.4, 2.5))


def scale_int(value: int, scale: float) -> int:
    """Scale số nguyên (thickness, padding, radius…) và giữ tối thiểu 1."""
    return max(1, int(round(value * scale)))


def scale_float(value: float, scale: float) -> float:
    """Scale font scale và giữ tối thiểu 0.1."""
    return max(0.1, value * scale)


def clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(int(value), hi))


# ─────────────────────────────────────────────────────────────────────────────
def draw_transparent_rect(
    frame: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color: tuple,
    alpha: float,
) -> None:
    """Vẽ hình chữ nhật đặc bán trong suốt lên frame (in-place)."""
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
    cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, frame)


# ─────────────────────────────────────────────────────────────────────────────
def put_text(
    frame: np.ndarray,
    text: str,
    origin: tuple[int, int],
    *,
    font: int = cv2.FONT_HERSHEY_SIMPLEX,
    font_scale: float = 0.6,
    color: tuple = (255, 255, 255),
    thickness: int = 1,
) -> None:
    """Shorthand putText với LINE_AA luôn bật."""
    cv2.putText(frame, text, origin, font, font_scale, color, thickness, cv2.LINE_AA)
