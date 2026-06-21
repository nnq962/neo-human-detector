"""
Bảng màu dùng trong module visualization.

Màu theo định dạng BGR (OpenCV).
"""

from __future__ import annotations


# ─── Pose ─────────────────────────────────────────────────────────────────────
# Màu theo bên trái/phải cơ thể người (góc nhìn của người đó)
POSE_LEFT_COLOR   = (0, 200, 50)     # xanh lá — bên trái người
POSE_RIGHT_COLOR  = (255, 80, 0)     # xanh dương — bên phải người
POSE_CENTER_COLOR = (0, 220, 220)    # vàng nhạt — đường trục giữa
POSE_KP_COLOR     = (255, 255, 255)  # trắng — tâm keypoint
POSE_KP_BORDER    = (30, 30, 30)     # viền tối cho keypoint

# ─── Bbox ReID status ─────────────────────────────────────────────────────────
STATUS_COLORS: dict[str | None, tuple[int, int, int]] = {
    "confirmed" : (0, 220, 0),     # xanh lá — đã xác nhận danh tính
    "uncertain" : (0, 165, 255),   # cam — đang chờ xác nhận
    "new"       : (200, 200, 200), # xám — mới xuất hiện, chưa có ID
    None        : (100, 100, 100), # xám tối — không có thông tin
}

# ─── Zone state ───────────────────────────────────────────────────────────────
ZONE_EMPTY         = (0, 0, 220)
ZONE_PENDING_ENTER = (0, 165, 255)
ZONE_OCCUPIED      = (0, 200, 0)
ZONE_PENDING_EXIT  = (0, 255, 255)
ZONE_FALLBACK      = (255, 255, 255)


# ─────────────────────────────────────────────────────────────────────────────
# Palette 20 màu phân biệt tốt trên nền tối, dùng cho track_id / global_id.
_ID_PALETTE: list[tuple[int, int, int]] = [
    (255, 80,  80 ),
    (80,  200, 255),
    (80,  255, 80 ),
    (255, 200, 80 ),
    (200, 80,  255),
    (80,  255, 200),
    (255, 80,  200),
    (80,  140, 255),
    (255, 160, 80 ),
    (140, 255, 80 ),
    (255, 80,  140),
    (80,  255, 140),
    (200, 200, 80 ),
    (80,  200, 200),
    (200, 80,  200),
    (255, 120, 50 ),
    (50,  180, 255),
    (180, 255, 50 ),
    (255, 50,  120),
    (120, 50,  255),
]


def id_color(id_value: int) -> tuple[int, int, int]:
    """Trả màu BGR nhất quán theo ID (track_id hoặc global_id)."""
    return _ID_PALETTE[int(id_value) % len(_ID_PALETTE)]


def bbox_color(status: str | None) -> tuple[int, int, int]:
    """Trả màu bbox theo trạng thái ReID."""
    return STATUS_COLORS.get(status, STATUS_COLORS[None])
