"""Các kiểu dữ liệu dùng bởi tầng ra quyết định điều phối robot."""

from dataclasses import dataclass
from enum import Enum

from src.zones_management import Zone, ZoneState


# ─────────────────────────────────────────────────────────────────────────────
class DispatchAction(Enum):
    """Các loại quyết định mà tầng dispatcher cần xử lý."""

    TASK_ASSIGN = "TASK_ASSIGN"
    TASK_CANCEL = "TASK_CANCEL"

    # Tên tương thích với contract cũ của RobotDispatcherV2.
    REQUEST_SERVICE = TASK_ASSIGN
    ZONE_CLEARED = TASK_CANCEL


# ─────────────────────────────────────────────────────────────────────────────
class ZoneServiceState(Enum):
    """Trạng thái phục vụ độc lập với trạng thái vision của zone."""

    NOT_REQUESTED = "NOT_REQUESTED"  # Zone chưa từng sinh yêu cầu giao task.
    ACTIVE        = "ACTIVE"         # Zone đã sinh yêu cầu giao task và task đó chưa được báo hoàn tất.
    COMPLETED     = "COMPLETED"      # Zone đã sinh yêu cầu giao task và task đó đã được báo hoàn tất.


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ZoneDecisionState:
    """State gần nhất mà decision engine đang giữ cho một zone."""

    previous_zone_state: ZoneState
    service_state: ZoneServiceState = ZoneServiceState.NOT_REQUESTED


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DispatchDecision:
    """Quyết định bất biến cùng transition đã tạo ra quyết định đó."""

    action: DispatchAction
    zone_id: str
    zone: Zone
    previous_state: ZoneState
    current_state: ZoneState
