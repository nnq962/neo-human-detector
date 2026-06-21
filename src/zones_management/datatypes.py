"""
Kiểu dữ liệu chuẩn cho zone trong pipeline mới.

Module này là nơi duy nhất nên chứa state/runtime data của zone. Các phần khác
như camera loader, geometry, state machine và output chỉ đọc/ghi thông qua model
này để sau này mở rộng tracking/ReID/UART dễ hơn.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
class ZoneState(Enum):
    """Các trạng thái vòng đời của một zone."""

    EMPTY = "EMPTY"
    PENDING_ENTER = "PENDING_ENTER"
    OCCUPIED = "OCCUPIED"
    PENDING_EXIT = "PENDING_EXIT"


# ─────────────────────────────────────────────────────────────────────────────
class ZoneColor:
    """Bảng màu BGR dùng khi vẽ zone bằng OpenCV."""

    EMPTY = (0, 0, 220)
    PENDING_ENTER = (0, 165, 255)
    OCCUPIED = (0, 200, 0)
    PENDING_EXIT = (0, 255, 255)
    FALLBACK = (255, 255, 255)

    @classmethod
    def get_color(cls, state: ZoneState) -> tuple:
        """Lấy màu tương ứng với trạng thái zone."""
        mapping = {
            ZoneState.EMPTY: cls.EMPTY,
            ZoneState.PENDING_ENTER: cls.PENDING_ENTER,
            ZoneState.OCCUPIED: cls.OCCUPIED,
            ZoneState.PENDING_EXIT: cls.PENDING_EXIT,
        }

        return mapping.get(state, cls.FALLBACK)


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Zone:
    """
    Zone runtime thuộc một camera.

    `pts` là polygon pixel gốc dạng ndarray shape (N, 2). Các field thời gian
    được state machine cập nhật trực tiếp để giữ trạng thái liên tục qua frame.
    """

    camera_id  : str
    camera_name: str
    name       : str
    pts        : np.ndarray
    goal_pose  : Dict[str, Any]
    id         : Optional[str] = None
    state      : ZoneState = ZoneState.EMPTY
    enter_time : float = 0.0
    lost_time  : float = 0.0

    @property
    def key(self) -> str:
        """Định danh duy nhất của zone trong hệ multi-camera."""
        return f"{self.camera_id}.{self.name}"

    def get_current_color(self) -> tuple:
        """Lấy màu hiện tại để vẽ polygon/label."""
        return ZoneColor.get_color(self.state)

    def reset_zone(self) -> None:
        """Reset zone về trạng thái trống nhưng giữ metadata camera/goal_pose."""
        self.state = ZoneState.EMPTY
        self.enter_time = 0.0
        self.lost_time = 0.0
