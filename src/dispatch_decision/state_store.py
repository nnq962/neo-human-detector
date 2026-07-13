"""Kho trạng thái vision và trạng thái phục vụ của từng zone."""

import threading
from typing import Dict, Optional

from src.dispatch_decision.datatypes import ZoneDecisionState, ZoneServiceState
from src.zones_management import ZoneState


# ─────────────────────────────────────────────────────────────────────────────
class DispatchDecisionStateStore:
    """Lưu state của từng zone và cho phép đọc/cập nhật an toàn giữa các thread."""

    def __init__(self) -> None:
        """Khởi tạo kho trạng thái rỗng."""
        self._lock = threading.RLock()
        self._states: Dict[str, ZoneDecisionState] = {}

    def get(self, zone_id: str) -> Optional[ZoneDecisionState]:
        """Lấy state của zone, hoặc ``None`` nếu zone chưa từng được quan sát."""
        with self._lock:
            return self._states.get(zone_id)

    def initialize(self, zone_id: str, zone_state: ZoneState) -> ZoneDecisionState:
        """Khởi tạo zone nếu chưa tồn tại và trả state hiện có của zone."""
        with self._lock:
            return self._states.setdefault(
                zone_id,
                ZoneDecisionState(previous_zone_state=zone_state),
            )

    def update_zone_state(self, zone_id: str, zone_state: ZoneState) -> None:
        """Cập nhật state vision mới nhất nhưng giữ nguyên trạng thái phục vụ."""
        with self._lock:
            current = self._states[zone_id]
            self._states[zone_id] = ZoneDecisionState(
                previous_zone_state=zone_state,
                service_state=current.service_state,
            )

    def set_service_state(
        self,
        zone_id: str,
        service_state: ZoneServiceState,
    ) -> None:
        """Cập nhật trạng thái phục vụ nhưng giữ nguyên state vision gần nhất."""
        with self._lock:
            current = self._states[zone_id]
            self._states[zone_id] = ZoneDecisionState(
                previous_zone_state=current.previous_zone_state,
                service_state=service_state,
            )

    def get_service_state(self, zone_id: str) -> ZoneServiceState:
        """Lấy trạng thái phục vụ; zone chưa quan sát được xem là chưa yêu cầu."""
        with self._lock:
            state = self._states.get(zone_id)
            if state is None:
                return ZoneServiceState.NOT_REQUESTED
            return state.service_state
