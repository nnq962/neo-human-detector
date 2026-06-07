"""
Visualization/debug overlay bằng OpenCV.

Các hàm trong file này chỉ dùng để vẽ preview debug. Pipeline sản phẩm vẫn nên
truyền dữ liệu qua WebSocket/UART thay vì phụ thuộc vào frame đã vẽ.
"""

from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from src.detection.detections import Detection
from src.models import Zone


COLOR_BBOX = (60, 100, 255)
COLOR_TRACK_TEXT = (255, 255, 255)
BASE_FRAME_HEIGHT = 1080
BASE_FONT_SCALE = 0.75
BASE_THICKNESS = 5
INFO_BLOCK_ALPHA = 0.45
BASE_INFO_BLOCK_PADDING_X = 12
BASE_INFO_BLOCK_PADDING_Y = 10
BASE_INFO_BLOCK_LINE_GAP = 14


# ─────────────────────────────────────────────────────────────────────────────
def draw_zones(frame: np.ndarray, zones: Sequence[Zone]) -> np.ndarray:
    """Vẽ lớp phủ polygon zone và trạng thái hiện tại lên frame."""
    overlay = frame.copy()

    for zone in zones:
        points = zone.pts
        color = zone.get_current_color()
        thickness = max(1, _get_draw_thickness(frame) // 2)

        cv2.fillPoly(overlay, [points], color=color)
        cv2.polylines(frame, [points], isClosed=True, color=color, thickness=thickness)
        _draw_zone_label(frame, zone, color)

    cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
    return frame


# ─────────────────────────────────────────────────────────────────────────────
def draw_detection_overlay(
    frame: np.ndarray,
    detections: Sequence[Detection],
    zone_names: Sequence[Optional[str]],
) -> np.ndarray:
    """Vẽ bbox Detection chuẩn, confidence, zone name và track id nếu có."""
    for detection, zone_name in zip(detections, zone_names):
        x1, y1, x2, y2 = map(int, detection.bbox)
        color = COLOR_BBOX
        label = _build_detection_label(detection, zone_name)
        thickness = _get_draw_thickness(frame)

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness=thickness)
        _draw_detection_label(frame, label, x1, y1, x2, y2, color)

    return frame


# ─────────────────────────────────────────────────────────────────────────────
def _draw_zone_label(frame: np.ndarray, zone: Zone, color: tuple) -> None:
    """Vẽ nhãn tên zone ở tâm polygon."""
    points = zone.pts
    label = f"{zone.name} [{zone.state.value}]"
    center_x = int(points[:, 0].mean())
    center_y = int(points[:, 1].mean())
    draw_scale = _get_draw_scale(frame)

    cv2.putText(
        frame,
        label,
        (center_x, center_y),
        cv2.FONT_HERSHEY_DUPLEX,
        _scale_float(0.8, draw_scale),
        color,
        max(1, _scale_int(2, draw_scale)),
    )


# ─────────────────────────────────────────────────────────────────────────────
def _draw_detection_label(
    frame: np.ndarray,
    label: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color: tuple,
) -> None:
    """Vẽ info block bán trong suốt ở mép trên bên trong bbox."""
    rows = _parse_detection_label(label)
    if not rows:
        return

    frame_height, frame_width = frame.shape[:2]
    x1 = _clamp(x1, 0, frame_width - 1)
    y1 = _clamp(y1, 0, frame_height - 1)
    x2 = _clamp(x2, x1 + 1, frame_width)
    y2 = _clamp(y2, y1 + 1, frame_height)

    draw_scale = _get_draw_scale(frame)
    border_inset = _get_draw_thickness(frame)
    inner_x1 = _clamp(x1 + border_inset, 0, frame_width - 1)
    inner_y1 = _clamp(y1 + border_inset, 0, frame_height - 1)
    inner_x2 = _clamp(x2 - border_inset, inner_x1 + 1, frame_width)
    inner_y2 = _clamp(y2 - border_inset, inner_y1 + 1, frame_height)

    if inner_x2 <= inner_x1 or inner_y2 <= inner_y1:
        return

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = _scale_float(BASE_FONT_SCALE, draw_scale)
    text_thickness = _scale_int(2, draw_scale)
    padding_x = _scale_int(BASE_INFO_BLOCK_PADDING_X, draw_scale)
    padding_y = _scale_int(BASE_INFO_BLOCK_PADDING_Y, draw_scale)
    line_gap = _scale_int(BASE_INFO_BLOCK_LINE_GAP, draw_scale)
    text_sizes = [
        cv2.getTextSize(_row_to_text(row), font, font_scale, text_thickness)[0]
        for row in rows
    ]
    text_height = max(height for _, height in text_sizes)
    block_width = inner_x2 - inner_x1
    block_height = min(
        len(rows) * text_height
        + (len(rows) - 1) * line_gap
        + padding_y * 2,
        inner_y2 - inner_y1,
    )

    block_x1 = inner_x1
    block_y1 = inner_y1
    block_x2 = block_x1 + block_width
    block_y2 = block_y1 + max(block_height, 1)

    _draw_transparent_rect(
        frame,
        block_x1,
        block_y1,
        block_x2,
        block_y2,
        (0, 0, 0),
        INFO_BLOCK_ALPHA,
    )

    text_x = block_x1 + padding_x
    text_y = block_y1 + padding_y + text_height
    column_layout = _build_label_column_layout(rows, font, font_scale, text_thickness, draw_scale)

    for row in rows:
        if text_y > block_y2 - padding_y:
            break

        _draw_label_row(
            frame,
            row,
            text_x,
            text_y,
            column_layout,
            font,
            font_scale,
            text_thickness,
        )
        text_y += text_height + line_gap


# ─────────────────────────────────────────────────────────────────────────────
def _draw_transparent_rect(
    frame: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color: tuple,
    alpha: float,
) -> None:
    """Vẽ rectangle bán trong suốt lên frame."""
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)


# ─────────────────────────────────────────────────────────────────────────────
def _parse_detection_label(label: str) -> List[Tuple[str, Optional[str]]]:
    """Tách label thành rows để render dạng cột key / ':' / value."""
    normalized = label.strip().strip("[]")
    if not normalized:
        return []

    lines = [part.strip() for part in normalized.split("] [") if part.strip()]
    rows: List[Tuple[str, Optional[str]]] = []
    for line in lines:
        if ":" not in line:
            rows.append((line, None))
            continue

        key, value = line.split(":", 1)
        rows.append((key.strip(), value.strip()))

    return rows


# ─────────────────────────────────────────────────────────────────────────────
def _build_label_column_layout(
    rows: List[Tuple[str, Optional[str]]],
    font: int,
    font_scale: float,
    text_thickness: int,
    draw_scale: float,
) -> dict:
    """Tính vị trí cột để dấu ':' thẳng hàng theo pixel."""
    key_widths = [
        cv2.getTextSize(key, font, font_scale, text_thickness)[0][0]
        for key, value in rows
        if value is not None
    ]
    colon_width = cv2.getTextSize(":", font, font_scale, text_thickness)[0][0]
    key_col_width = max(key_widths) if key_widths else 0
    gap = _scale_int(12, draw_scale)

    return {
        "colon_x": key_col_width + gap,
        "value_x": key_col_width + gap + colon_width + gap,
    }


# ─────────────────────────────────────────────────────────────────────────────
def _draw_label_row(
    frame: np.ndarray,
    row: Tuple[str, Optional[str]],
    x: int,
    y: int,
    column_layout: dict,
    font: int,
    font_scale: float,
    text_thickness: int,
) -> None:
    """Vẽ một dòng label theo layout cột."""
    key, value = row

    if value is None:
        cv2.putText(
            frame,
            key,
            (x, y),
            font,
            font_scale,
            COLOR_TRACK_TEXT,
            text_thickness,
            cv2.LINE_AA,
        )
        return

    cv2.putText(
        frame,
        key,
        (x, y),
        font,
        font_scale,
        COLOR_TRACK_TEXT,
        text_thickness,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        ":",
        (x + column_layout["colon_x"], y),
        font,
        font_scale,
        COLOR_TRACK_TEXT,
        text_thickness,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        value,
        (x + column_layout["value_x"], y),
        font,
        font_scale,
        COLOR_TRACK_TEXT,
        text_thickness,
        cv2.LINE_AA,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _row_to_text(row: Tuple[str, Optional[str]]) -> str:
    """Chuyển row về text đầy đủ để đo chiều cao dòng."""
    key, value = row
    if value is None:
        return key

    return f"{key}: {value}"


# ─────────────────────────────────────────────────────────────────────────────
def _clamp(value: int, min_value: int, max_value: int) -> int:
    """Giới hạn tọa độ trong frame."""
    return max(min_value, min(int(value), max_value))


# ─────────────────────────────────────────────────────────────────────────────
def _get_draw_scale(frame: np.ndarray) -> float:
    """Tính scale vẽ dựa trên chiều cao frame, lấy Full HD làm mốc 1.0."""
    frame_height = frame.shape[0]
    return max(0.65, min(frame_height / BASE_FRAME_HEIGHT, 2.4))


# ─────────────────────────────────────────────────────────────────────────────
def _get_draw_thickness(frame: np.ndarray) -> int:
    """Tính độ dày nét theo kích thước frame."""
    return _scale_int(BASE_THICKNESS, _get_draw_scale(frame))


# ─────────────────────────────────────────────────────────────────────────────
def _scale_int(value: int, scale: float) -> int:
    """Scale một số nguyên dùng cho pixel/padding/thickness."""
    return max(1, int(round(value * scale)))


# ─────────────────────────────────────────────────────────────────────────────
def _scale_float(value: float, scale: float) -> float:
    """Scale một số thực dùng cho font scale."""
    return max(0.1, value * scale)


# ─────────────────────────────────────────────────────────────────────────────
def _build_detection_label(detection: Detection, zone_name: Optional[str]) -> str:
    """Tạo text label nhiều dòng cho bbox."""
    parts = [
        f"tid: {detection.track_id if detection.track_id is not None else '-'}",
        f"gid: {_format_optional_id(_get_detection_attr(detection, 'global_id', 'gid'), width=2)}",
        f"cnf: {_format_percent(detection.confidence)}",
        f"sim: {_format_percent(_get_detection_attr(detection, 'similarity', 'sim'))}",
        f"sta: {_format_optional_text(_get_detection_attr(detection, 'status', 'state'))}",
        f"zon: {_format_optional_text(zone_name)}",
    ]

    return "[" + "] [".join(parts) + "]"


# ─────────────────────────────────────────────────────────────────────────────
def _get_detection_attr(detection: Detection, *names: str):
    """Lấy attribute mở rộng nếu Detection được gắn thêm data tracking/ReID."""
    for name in names:
        value = getattr(detection, name, None)
        if value is not None:
            return value

    return None


# ─────────────────────────────────────────────────────────────────────────────
def _format_optional_id(value, width: int = 2) -> str:
    """Format id dạng zero-pad, fallback '-' khi chưa có dữ liệu."""
    if value is None:
        return "-"

    try:
        return f"{int(value):0{width}d}"
    except (TypeError, ValueError):
        return str(value)


# ─────────────────────────────────────────────────────────────────────────────
def _format_percent(value) -> str:
    """Format confidence/similarity thành phần trăm nguyên."""
    if value is None:
        return "-"

    try:
        return f"{float(value) * 100:.0f}"
    except (TypeError, ValueError):
        return str(value)


# ─────────────────────────────────────────────────────────────────────────────
def _format_optional_text(value) -> str:
    """Format text ngắn, fallback '-' khi chưa có dữ liệu."""
    if value is None:
        return "-"

    return str(value)
