"""
Tầng nối giữa ReID, zone và robot service.

Module này trả lời câu hỏi nghiệp vụ: zone nào đang có global_id nào, global_id
đó đã được yêu cầu/phục vụ chưa, và có cần tạo request cho robot hay không.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from src.detection.detections import BBoxXYXY, DetectionFrame
from src.zones.models import Zone, ZoneState


# ─────────────────────────────────────────────────────────────────────────────
class IdentityServiceStatus(Enum):
    """Trạng thái phục vụ của một global_id trong runtime hiện tại."""

    NOT_SERVED = "not_served"
    REQUESTED  = "requested"
    SERVED     = "served"


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ZoneOccupant:
    """Một người cụ thể đang nằm trong một zone tại frame hiện tại."""

    camera_id      : str
    camera_name    : str
    zone_key       : str
    zone_name      : str
    detection_index: int
    bbox           : BBoxXYXY
    confidence     : float
    track_id       : Optional[int] = None
    global_id      : Optional[int] = None
    similarity     : Optional[float] = None
    status         : Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ZoneOccupancySnapshot:
    """Snapshot người theo zone của một camera/frame."""

    camera_id        : str
    camera_name      : str
    frame_idx        : int
    occupants_by_zone: Dict[str, List[ZoneOccupant]] = field(default_factory=dict)

    def zone_global_ids(self, zone_key: str) -> List[int]:
        """Trả danh sách global_id đã biết trong một zone."""
        global_ids: List[int] = []
        for occupant in self.occupants_by_zone.get(zone_key, []):
            if occupant.global_id is not None:
                global_ids.append(occupant.global_id)

        return global_ids


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class IdentityServiceState:
    """State dài hạn của một global_id dùng cho quyết định robot service."""

    global_id         : int
    service_status    : IdentityServiceStatus = IdentityServiceStatus.NOT_SERVED
    current_zone_key  : Optional[str] = None
    previous_zone_key : Optional[str] = None
    requested_zone_key: Optional[str] = None
    served_zone_key   : Optional[str] = None
    first_seen_frame  : int = 0
    last_seen_frame   : int = 0

    def move_to_zone(self, zone_key: str, frame_idx: int) -> None:
        """Cập nhật zone hiện tại, giữ lại zone trước đó nếu có thay đổi."""
        if self.current_zone_key != zone_key:
            self.previous_zone_key = self.current_zone_key
            self.current_zone_key = zone_key

        if self.first_seen_frame == 0:
            self.first_seen_frame = frame_idx
        self.last_seen_frame = frame_idx


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RobotServiceRequest:
    """Request đủ thông tin để output layer gửi sang robot."""

    request_id : str
    camera_id  : str
    camera_name: str
    zone_key   : str
    zone_name  : str
    global_id  : int
    track_id   : Optional[int]
    goal_pose  : Dict[str, Any]
    frame_idx  : int
    reason     : str


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ZoneOccupancyPolicy:
    """Policy quyết định khi nào tạo RobotServiceRequest."""

    require_confirmed_identity     : bool = True  # Chỉ tạo request khi ReID đã confirmed.
    require_occupied_zone          : bool = True  # Chỉ tạo request khi zone đang OCCUPIED.
    auto_mark_requested_on_dispatch: bool = True  # Tự chuyển sang REQUESTED sau khi tạo request để tránh gửi lặp.


# ─────────────────────────────────────────────────────────────────────────────
class ZoneOccupancyManager:
    """
    Quản lý occupancy theo global_id và phát request cho robot.

    Manager này không gửi robot trực tiếp. Nó chỉ trả `RobotServiceRequest`; output
    layer phía sau sẽ quyết định gửi UART/WebSocket/robot client.
    """

    def __init__(self, policy: ZoneOccupancyPolicy | None = None):
        self.policy = policy or ZoneOccupancyPolicy()
        self.identity_states: Dict[int, IdentityServiceState] = {}
        self.latest_snapshot: Optional[ZoneOccupancySnapshot] = None
        self.latest_requests: List[RobotServiceRequest] = []

    def update(
        self,
        snapshot: ZoneOccupancySnapshot,
        zones: Sequence[Zone],
    ) -> List[RobotServiceRequest]:
        """Cập nhật occupancy snapshot và trả danh sách request mới cho robot."""
        self.latest_snapshot = snapshot
        zone_by_key = {zone.key: zone for zone in zones}
        requests: List[RobotServiceRequest] = []

        for zone_key, occupants in snapshot.occupants_by_zone.items():
            zone = zone_by_key.get(zone_key)
            if zone is None:
                continue

            for occupant in occupants:
                if occupant.global_id is None:
                    continue

                # Cập nhật hồ sơ dài hạn của global_id này.
                state = self._update_identity_state(occupant, snapshot.frame_idx)
                # Snapshot có thể chứa người ở zone chưa OCCUPIED; robot service
                # chỉ được phát khi zone đã đủ điều kiện nghiệp vụ.
                if not self._is_zone_allowed_for_service(zone):
                    continue

                # Kiểm tra policy còn lại: identity đã confirmed và global_id này
                # chưa từng được request/served trong runtime hiện tại.
                if not self._should_request_service(occupant, state):
                    continue

                request = self._build_request(occupant, zone, snapshot.frame_idx)
                requests.append(request)
                self._mark_requested(state, request)

        self.latest_requests = requests
        return requests

    def mark_served(
        self,
        global_id: int,
        *,
        zone_key: Optional[str] = None,
        frame_idx: Optional[int] = None,
    ) -> None:
        """Đánh dấu một global_id đã được robot phục vụ."""
        state = self.identity_states.get(global_id)
        if state is None:
            state = IdentityServiceState(global_id=global_id)
            self.identity_states[global_id] = state

        state.service_status = IdentityServiceStatus.SERVED
        state.served_zone_key = zone_key or state.current_zone_key
        if frame_idx is not None:
            state.last_seen_frame = frame_idx

    def reset_identity(self, global_id: int) -> None:
        """Xóa state phục vụ của một global_id."""
        self.identity_states.pop(global_id, None)

    def get_zone_occupants(self, zone_key: str) -> List[ZoneOccupant]:
        """Lấy occupants mới nhất của một zone."""
        if self.latest_snapshot is None:
            return []

        return list(self.latest_snapshot.occupants_by_zone.get(zone_key, []))

    def get_zone_global_ids(self, zone_key: str) -> List[int]:
        """Lấy global_id mới nhất trong một zone."""
        if self.latest_snapshot is None:
            return []

        return self.latest_snapshot.zone_global_ids(zone_key)

    def get_identity_state(self, global_id: int) -> Optional[IdentityServiceState]:
        """Lấy state phục vụ của một global_id."""
        return self.identity_states.get(global_id)

    def _update_identity_state(
        self,
        occupant: ZoneOccupant,
        frame_idx: int,
    ) -> IdentityServiceState:
        """
        Cập nhật zone hiện tại của global_id.
        Tạo state dài hạn cho global_id nếu chưa có.
        Nếu global_id đã tồn tại, cập nhật zone và frame cuối cùng thấy để phục vụ quyết định sau này.
        """
        assert occupant.global_id is not None
        state = self.identity_states.get(occupant.global_id)
        if state is None:
            state = IdentityServiceState(
                global_id=occupant.global_id,
                first_seen_frame=frame_idx,
            )
            self.identity_states[occupant.global_id] = state

        state.move_to_zone(occupant.zone_key, frame_idx)
        return state

    def _is_zone_allowed_for_service(self, zone: Zone) -> bool:
        """Kiểm tra zone có đủ điều kiện phát request robot hay chưa."""
        if not self.policy.require_occupied_zone:
            return True

        return zone.state == ZoneState.OCCUPIED

    def _should_request_service(
        self,
        occupant: ZoneOccupant,
        state: IdentityServiceState,
    ) -> bool:
        """Kiểm tra occupant này có cần tạo request mới không."""
        if self.policy.require_confirmed_identity and occupant.status != "confirmed":
            return False

        return state.service_status == IdentityServiceStatus.NOT_SERVED

    def _mark_requested(
        self,
        state: IdentityServiceState,
        request: RobotServiceRequest,
    ) -> None:
        """Đánh dấu identity đã được tạo service request để tránh gửi lặp."""
        state.requested_zone_key = request.zone_key
        if self.policy.auto_mark_requested_on_dispatch:
            state.service_status = IdentityServiceStatus.REQUESTED

    def _build_request(
        self,
        occupant: ZoneOccupant,
        zone: Zone,
        frame_idx: int,
    ) -> RobotServiceRequest:
        """Đóng gói RobotServiceRequest từ occupant và zone."""
        assert occupant.global_id is not None
        request_id = f"{frame_idx}:{occupant.camera_id}:{occupant.zone_name}:{occupant.global_id}"

        return RobotServiceRequest(
            request_id=request_id,
            camera_id=occupant.camera_id,
            camera_name=occupant.camera_name,
            zone_key=occupant.zone_key,
            zone_name=occupant.zone_name,
            global_id=occupant.global_id,
            track_id=occupant.track_id,
            goal_pose=zone.goal_pose,
            frame_idx=frame_idx,
            reason="new_identity_in_zone",
        )


# ─────────────────────────────────────────────────────────────────────────────
def build_zone_occupancy_snapshot(
    *,
    camera: Any,
    detection_frame: DetectionFrame,
    zones: Sequence[Zone],
    zone_names: Sequence[Optional[str]],
    frame_idx: int,
) -> ZoneOccupancySnapshot:
    """Tạo snapshot occupants từ DetectionFrame đã được enrich ReID."""
    zone_by_name = {zone.name: zone for zone in zones}
    occupants_by_zone: Dict[str, List[ZoneOccupant]] = {
        zone.key: []
        for zone in zones
    }

    for index, detection in enumerate(detection_frame.detections):
        zone_name = zone_names[index] if index < len(zone_names) else None
        if zone_name is None:
            continue

        zone = zone_by_name.get(zone_name)
        if zone is None:
            continue

        occupants_by_zone.setdefault(zone.key, []).append(
            ZoneOccupant(
                camera_id=str(camera.id),
                camera_name=str(camera.name),
                zone_key=zone.key,
                zone_name=zone.name,
                detection_index=index,
                bbox=detection.bbox,
                confidence=float(detection.confidence),
                track_id=detection.track_id,
                global_id=detection.global_id,
                similarity=detection.similarity,
                status=detection.status,
            )
        )

    return ZoneOccupancySnapshot(
        camera_id=str(camera.id),
        camera_name=str(camera.name),
        frame_idx=frame_idx,
        occupants_by_zone=occupants_by_zone,
    )
