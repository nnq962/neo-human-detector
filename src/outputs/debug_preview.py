"""
Helper vẽ/chuẩn bị frame preview debug bằng OpenCV.

Module này chỉ phục vụ màn hình debug khi runtime bật `show=True`. Các payload
sản phẩm như WebSocket/UART không nên phụ thuộc vào frame đã vẽ.
"""

import cv2
from unidecode import unidecode

from src.detection.detections import DetectionFrame


# ─────────────────────────────────────────────────────────────────────────────
def extract_raw_frame(detection_frame: DetectionFrame):
    """Lấy frame gốc từ raw YOLO result để vẽ debug."""
    raw_result = detection_frame.raw_result
    raw_frame = getattr(raw_result, "orig_img", None)

    if raw_frame is None:
        return None

    return raw_frame.copy()


# ─────────────────────────────────────────────────────────────────────────────
def draw_fps_label(frame, camera_name: str, fps: float, detection_count: int) -> None:
    """Vẽ thanh trạng thái full-width ở đầu frame."""
    frame_height, frame_width = frame.shape[:2]
    draw_scale = _get_draw_scale(frame)
    font_scale = _scale_float(1.0, draw_scale)
    thickness = _scale_int(2, draw_scale)
    padding_x = _scale_int(14, draw_scale)
    padding_bottom = _scale_int(14, draw_scale)
    bar_height = max(_scale_int(52, draw_scale), int(frame_height * 0.045))
    label = (
        f"{_format_camera_label(camera_name)} - "
        f"{frame_width}x{frame_height} - "
        f"{detection_count} {_person_label(detection_count)} detected - "
        f"{int(round(fps))} fps"
    )

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (frame_width, bar_height), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

    cv2.putText(
        frame,
        label,
        (padding_x, min(bar_height - padding_bottom, _scale_int(36, draw_scale))),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )


# ─────────────────────────────────────────────────────────────────────────────
def resize_frame(frame, scale: float):
    """Resize frame debug theo show_scale."""
    height, width = frame.shape[:2]
    new_dim = (int(width * scale), int(height * scale))

    return cv2.resize(frame, new_dim)


# ─────────────────────────────────────────────────────────────────────────────
def _format_camera_label(camera_name: str) -> str:
    """Chuẩn hóa tên camera cho status bar."""
    normalized = unidecode(str(camera_name)).strip()
    return normalized


# ─────────────────────────────────────────────────────────────────────────────
def _person_label(count: int) -> str:
    """Trả nhãn person/persons theo số lượng detection."""
    return "person" if count == 1 else "persons"


# ─────────────────────────────────────────────────────────────────────────────
def _get_draw_scale(frame) -> float:
    """Tính scale vẽ dựa trên chiều cao frame, lấy Full HD làm mốc 1.0."""
    frame_height = frame.shape[0]
    return max(0.65, min(frame_height / 1080, 2.4))


# ─────────────────────────────────────────────────────────────────────────────
def _scale_int(value: int, scale: float) -> int:
    """Scale một số nguyên dùng cho pixel/padding/thickness."""
    return max(1, int(round(value * scale)))


# ─────────────────────────────────────────────────────────────────────────────
def _scale_float(value: float, scale: float) -> float:
    """Scale một số thực dùng cho font scale."""
    return max(0.1, value * scale)
