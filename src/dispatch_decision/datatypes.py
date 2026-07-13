"""Các kiểu dữ liệu của tầng ra quyết định dispatch theo trạng thái zone."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.zones_management import Zone, ZoneState


# ─────────────────────────────────────────────────────────────────────────────
class DispatchAction(Enum):
    """Hành động mà tầng thực thi robot cần xử lý."""

    TASK_ASSIGN = "TASK_ASSIGN"
    TASK_CANCEL = "TASK_CANCEL"


# ─────────────────────────────────────────────────────────────────────────────
class ZoneServiceState(Enum):
    """Trạng thái phục vụ hiện tại của một zone."""

    # Occupancy hiện tại chưa sinh TASK_ASSIGN.
    NOT_REQUESTED = "NOT_REQUESTED"

    # Đã sinh TASK_ASSIGN cho occupancy hiện tại nhưng chưa được báo hoàn thành.
    REQUESTED = "REQUESTED"

    # Task đã hoàn thành; khi zone EMPTY thì không cần cancel.
    COMPLETED = "COMPLETED"

    # Robot báo task thất bại; không tự retry trong cùng lượt occupancy.
    FAILED = "FAILED"


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ZoneDecisionState:
    """State mà decision engine đang lưu cho một zone."""

    last_zone_state: ZoneState
    service_state: ZoneServiceState = ZoneServiceState.NOT_REQUESTED


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DispatchDecision:
    """Quyết định được sinh ra từ một transition trạng thái zone."""

    action: DispatchAction
    zone_id: str
    zone: Zone
    previous_state: ZoneState
    current_state: ZoneState
