from enum import Enum
from dataclasses import dataclass
import numpy as np

# ────────────────────────────────────────────────────────────────
# Định nghĩa các trạng thái Zone
class ZoneState(Enum):
    EMPTY = "EMPTY"                 # Ghế trống
    PENDING_ENTER = "PENDING_ENTER" # Có người chạm vào Zone, chờ đủ 10s
    OCCUPIED = "OCCUPIED"           # Đã xác nhận có người dùng ghế
    PENDING_EXIT = "PENDING_EXIT"   # Mất bbox trong zone, chờ xác nhận rời đi

# ────────────────────────────────────────────────────────────────
# Class quản lý bảng màu sắc (Hệ BGR của OpenCV)
class ZoneColor:
    EMPTY = (0, 0, 220)           # Đỏ: Trống
    PENDING_ENTER = (0, 165, 255) # Cam: Đang chờ xác nhận vào
    OCCUPIED = (0, 200, 0)        # Xanh lá: Đã xác nhận có người
    PENDING_EXIT = (0, 255, 255)  # Vàng: Đang chờ xác nhận ra

    @classmethod
    def get_color(cls, state: ZoneState) -> tuple:
        """Hàm tiện ích để lấy màu tương ứng với Enum trạng thái"""
        mapping = {
            ZoneState.EMPTY: cls.EMPTY,
            ZoneState.PENDING_ENTER: cls.PENDING_ENTER,
            ZoneState.OCCUPIED: cls.OCCUPIED,
            ZoneState.PENDING_EXIT: cls.PENDING_EXIT
        }
        return mapping.get(state, (255, 255, 255)) # Trả về màu Trắng nếu có lỗi

# ────────────────────────────────────────────────────────────────
# Dataclass quản lý Vùng giám sát (Zone)
@dataclass
class Zone:
    """Class lưu trữ toàn bộ trạng thái và thông tin của một vùng Zone"""
    name: str
    pts: np.ndarray
    goal_pose: dict
    
    # Quản lý trạng thái
    state: ZoneState = ZoneState.EMPTY
    
    # Quản lý thời gian
    enter_time: float = 0.0      # Mốc thời gian bbox bắt đầu xuất hiện trong Zone
    lost_time: float = 0.0       # Mốc thời gian bbox biến mất khỏi Zone
    
    # 4. Dữ liệu mở rộng (Extendable)
    is_served: bool = False      # Trạng thái phục vụ (VD: robot đã mang đồ ăn ra chưa)
    occupied_duration: float = 0.0 # Tổng thời gian khách đã ngồi (tính bằng giây)

    def get_current_color(self) -> tuple:
        """Gọi nhanh hàm này khi cần vẽ cv2.polylines hoặc cv2.putText"""
        return ZoneColor.get_color(self.state)

    def reset_zone(self):
        """Hàm tiện ích để reset ghế về trạng thái trống"""
        self.state = ZoneState.EMPTY
        self.enter_time = 0.0
        self.lost_time = 0.0
        self.is_served = False
        self.occupied_duration = 0.0
