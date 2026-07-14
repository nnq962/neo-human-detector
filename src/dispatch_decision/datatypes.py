"""Các kiểu dữ liệu của tầng ra quyết định dispatch theo trạng thái zone."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

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

    # Đã sinh TASK_CANCEL nhưng tầng thực thi chưa xác nhận cancel hoàn tất.
    CANCEL_REQUESTED = "CANCEL_REQUESTED"

    # Task đã hoàn thành; khi zone EMPTY thì không cần cancel.
    COMPLETED = "COMPLETED"

    # Robot báo task thất bại; không tự retry trong cùng lượt occupancy.
    FAILED = "FAILED"


# ─────────────────────────────────────────────────────────────────────────────
class PersonServiceState(Enum):
    """Trạng thái phục vụ toàn cục của một người theo global ID."""

    # Đã sinh TASK_ASSIGN và service chưa kết thúc.
    REQUESTED = "REQUESTED"

    # Robot đã báo hoàn thành; không mời lại trong phiên runtime hiện tại.
    SERVED = "SERVED"


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class PersonServiceRecord:
    """Thông tin service đang chặn yêu cầu mới của một người."""

    state: PersonServiceState
    zone_id: str


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ZoneDecisionState:
    """
    State mà decision engine đang lưu cho một zone.

        - last_zone_state: trạng thái zone gần nhất được quan sát.
        - service_state: trạng thái phục vụ hiện tại của zone.
        - awaiting_identity: True nếu zone đang chờ một người có global ID.
        - active_person_global_id: global ID của occupancy hiện tại nếu có.
    """

    last_zone_state: ZoneState
    service_state: ZoneServiceState = ZoneServiceState.NOT_REQUESTED
    awaiting_identity: bool = False
    awaiting_reassignment: bool = False
    observed_person_global_id: Optional[int] = None
    active_person_global_id: Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DispatchDecision:
    """
    Quyết định được sinh ra từ một transition trạng thái zone.

        - action: hành động mà tầng thực thi robot cần thực hiện.
        - zone_id: ID của zone mà quyết định này liên quan.
        - zone: thông tin zone hiện tại.
        - previous_state: trạng thái zone trước khi transition.
        - current_state: trạng thái zone sau khi transition.
        - person_global_id: global ID của occupancy hiện tại nếu có.
        - person_similarity: độ tương đồng của occupancy hiện tại nếu có.
        - person_track_id: track ID của occupancy hiện tại nếu có.
    """

    action: DispatchAction
    zone_id: str
    zone: Zone
    previous_state: ZoneState
    current_state: ZoneState
    person_global_id: Optional[int] = None
    person_similarity: Optional[float] = None
    person_track_id: Optional[int] = None
