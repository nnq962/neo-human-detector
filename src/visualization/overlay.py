"""
Overlay thông tin chung lên frame: status bar, FPS, resize.
"""

from __future__ import annotations

import cv2
import numpy as np
from unidecode import unidecode

from src.visualization.utils import (
    draw_transparent_rect,
    get_draw_scale,
    put_text,
    scale_float,
    scale_int,
)


# ─────────────────────────────────────────────────────────────────────────────
def draw_status_bar(
    frame           : np.ndarray,
    *,
    camera_name     : str,
    fps             : float,
    detection_count : int,
    extra           : str = "",
) -> None:
    """
    Vẽ thanh trạng thái full-width ở đầu frame.

    Hiển thị: tên camera, resolution, số người, FPS và text tuỳ chọn.
    """
    h, w  = frame.shape[:2]
    scale = get_draw_scale(frame)

    bar_h      = max(scale_int(48, scale), int(h * 0.042))
    font_scale = scale_float(0.85, scale)
    thickness  = scale_int(2, scale)
    pad_x      = scale_int(14, scale)

    name_clean = unidecode(str(camera_name).strip())
    label = (
        f"{name_clean}  |  {w}x{h}"
        f"  |  {detection_count} {'person' if detection_count == 1 else 'persons'}"
        f"  |  {fps:.1f} fps"
    )
    if extra:
        label += f"  |  {extra}"

    draw_transparent_rect(frame, 0, 0, w, bar_h, (0, 0, 0), alpha=0.50)

    # Căn text theo chiều cao bar
    (_, text_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
    text_y = (bar_h + text_h) // 2

    put_text(
        frame,
        label,
        (pad_x, text_y),
        font=cv2.FONT_HERSHEY_SIMPLEX,
        font_scale=font_scale,
        color=(255, 255, 255),
        thickness=thickness,
    )


# ─────────────────────────────────────────────────────────────────────────────
def draw_label(
    frame    : np.ndarray,
    text     : str,
    position : tuple[int, int],
    *,
    color    : tuple[int, int, int] = (255, 255, 255),
    bg_color : tuple[int, int, int] = (0, 0, 0),
    bg_alpha : float = 0.45,
) -> None:
    """
    Vẽ text có nền bán trong suốt tại vị trí bất kỳ.

    Dùng cho các nhãn debug tuỳ ý ngoài status bar.
    """
    scale      = get_draw_scale(frame)
    font       = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = scale_float(0.65, scale)
    thickness  = scale_int(1, scale)
    pad_x      = scale_int(8, scale)
    pad_y      = scale_int(5, scale)

    (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    x, y = position

    draw_transparent_rect(
        frame,
        x - pad_x,
        y - text_h - pad_y,
        x + text_w + pad_x,
        y + baseline + pad_y,
        bg_color,
        bg_alpha,
    )
    put_text(frame, text, (x, y), font=font, font_scale=font_scale,
             color=color, thickness=thickness)


# ─────────────────────────────────────────────────────────────────────────────
def resize_for_display(frame: np.ndarray, scale: float) -> np.ndarray:
    """Resize frame để preview, giữ nguyên aspect ratio."""
    if scale == 1.0:
        return frame
    h, w = frame.shape[:2]
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    return cv2.resize(frame, (new_w, new_h))
