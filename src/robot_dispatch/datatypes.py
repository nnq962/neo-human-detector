"""
Kiểu dữ liệu chuẩn cho request gửi robot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from src.zones_management import Zone, ZoneState


# ─────────────────────────────────────────────────────────────────────────────
class RobotDispatchEvent(Enum):
    """Các loại event mà robot dispatcher có thể phát ra."""

    ZONE_OCCUPIED = "ZONE_OCCUPIED"
    ZONE_CLEARED = "ZONE_CLEARED"


# ─────────────────────────────────────────────────────────────────────────────
class PersonServiceState(Enum):
    """Trạng thái phục vụ của một người trong phiên runtime hiện tại."""

    NEW       = "NEW"
    REQUESTED = "REQUESTED"
    SERVING   = "SERVING"
    SERVED    = "SERVED"
    SKIPPED   = "SKIPPED"
    EXPIRED   = "EXPIRED"
    CANCELLED = "CANCELLED"
    FAILED    = "FAILED"


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class PersonServiceRecord:
    """Thông tin request phục vụ mới nhất của một người."""

    state     : PersonServiceState
    updated_at: float
    request_id: str
    zone_id   : str


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RobotDispatchConfig:
    """Cấu hình điều khiển việc sinh request cho robot từ runtime."""

    enabled                 : bool = False
    emit_occupied           : bool = True
    emit_cleared            : bool = False
    raise_on_transport_error: bool = False
    require_reid            : bool = True
    fallback_without_reid   : bool = False
    service_ttl_minutes     : Optional[float] = None


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RobotDispatchRequest:
    """Payload nội bộ đại diện cho một request điều hướng robot tới zone."""

    request_id      : str
    event           : RobotDispatchEvent
    camera_id       : str
    camera_name     : str
    zone_id         : Optional[str]
    zone_name       : str
    state           : ZoneState
    goal_pose       : Dict[str, Any]
    timestamp       : float
    person_global_id: Optional[int] = None
    similarity      : Optional[float] = None
    metadata        : Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Chuyển request sang dict an toàn để log, serialize hoặc gửi network."""
        return {
            "request_id": self.request_id,
            "event": self.event.value,
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "state": self.state.value,
            "goal_pose": dict(self.goal_pose),
            "timestamp": float(self.timestamp),
            "person_global_id": self.person_global_id,
            "similarity": self.similarity,
            "metadata": dict(self.metadata),
        }


# ─────────────────────────────────────────────────────────────────────────────
def build_zone_dispatch_request(
    *,
    zone: Zone,
    event: RobotDispatchEvent,
    timestamp: float,
    person_global_id: Optional[int] = None,
    similarity: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> RobotDispatchRequest:
    """Tạo request robot từ dữ liệu zone hiện tại."""
    request_ts = zone.enter_time if zone.enter_time > 0 else timestamp
    identity_part = f":person:{person_global_id}" if person_global_id is not None else ""
    zone_identity = zone.id or f"{zone.camera_id}:{zone.name}"
    request_id = f"{zone_identity}:{event.value}{identity_part}:{int(request_ts * 1000)}"

    return RobotDispatchRequest(
        request_id=request_id,
        event=event,
        camera_id=zone.camera_id,
        camera_name=zone.camera_name,
        zone_id=zone.id,
        zone_name=zone.name,
        state=zone.state,
        goal_pose=dict(zone.goal_pose),
        timestamp=float(timestamp),
        person_global_id=person_global_id,
        similarity=similarity,
        metadata=metadata or {},
    )
