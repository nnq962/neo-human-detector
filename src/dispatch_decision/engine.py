"""Điều phối việc lưu state và áp dụng policy cho từng frame vision."""

import threading
from typing import List, Optional, Sequence

from src.dispatch_decision.datatypes import (
    DispatchAction,
    DispatchDecision,
    ZoneServiceState,
)
from src.dispatch_decision.policy import ZoneOnlyDecisionPolicy
from src.dispatch_decision.state_store import DispatchDecisionStateStore
from src.zones_management import Zone, ZoneState


# ─────────────────────────────────────────────────────────────────────────────
class DispatchDecisionEngine:
    """Sinh decision từ transition zone và vòng đời phục vụ hiện tại."""

    def __init__(
        self,
        *,
        state_store: Optional[DispatchDecisionStateStore] = None,
        policy: Optional[ZoneOnlyDecisionPolicy] = None,
    ) -> None:
        """Khởi tạo engine với state store và policy mặc định nếu không truyền vào."""
        self._state_store = state_store or DispatchDecisionStateStore()
        self._policy = policy or ZoneOnlyDecisionPolicy()
        self._lock = threading.RLock()

    def process_zones(self, zones: Sequence[Zone]) -> List[DispatchDecision]:
        """
        Xử lý snapshot zone sau một lần state machine update.

        Lần đầu thấy một zone chỉ khởi tạo lịch sử và không sinh decision.
        """
        decisions: List[DispatchDecision] = []
        with self._lock:
            for zone in zones:
                # Get id
                zone_id = _get_zone_id(zone)
                # Get stored state
                stored = self._state_store.get(zone_id)
                # Nếu chưa tồn tại thì khởi tạo và bỏ qua lần đầu tiên.
                if stored is None:
                    self._state_store.initialize(zone_id, zone.state)
                    continue
                
                # Sinh action từ trạng thái cũ, trạng thái mới và trạng thái phục vụ hiện tại.
                action = self._policy.decide(
                    stored.previous_zone_state,
                    zone.state,
                    stored.service_state,
                )

                # 
                self._state_store.update_zone_state(zone_id, zone.state)

                if action is DispatchAction.TASK_ASSIGN:
                    self._state_store.set_service_state(
                        zone_id,
                        ZoneServiceState.ACTIVE,
                    )
                elif action is DispatchAction.TASK_CANCEL:
                    self._state_store.set_service_state(
                        zone_id,
                        ZoneServiceState.NOT_REQUESTED,
                    )

                if action is not None:
                    decisions.append(
                        DispatchDecision(
                            action=action,
                            zone_id=zone_id,
                            zone=zone,
                            previous_state=stored.previous_zone_state,
                            current_state=zone.state,
                        )
                    )

                if (
                    stored.previous_zone_state is ZoneState.PENDING_EXIT
                    and zone.state is ZoneState.EMPTY
                    and stored.service_state is ZoneServiceState.COMPLETED
                ):
                    self._state_store.set_service_state(
                        zone_id,
                        ZoneServiceState.NOT_REQUESTED,
                    )

        return decisions

    def on_service_completed(self, zone_id: str) -> bool:
        """Đánh dấu service hoàn tất; trả ``False`` nếu zone không có task active."""
        with self._lock:
            if self._state_store.get_service_state(zone_id) is not ZoneServiceState.ACTIVE:
                return False
            self._state_store.set_service_state(zone_id, ZoneServiceState.COMPLETED)
            return True

    def get_service_state(self, zone_id: str) -> ZoneServiceState:
        """Lấy trạng thái phục vụ hiện tại của zone."""
        with self._lock:
            return self._state_store.get_service_state(zone_id)

    def has_active_service(self, zone_id: str) -> bool:
        """Kiểm tra zone có task đang hoạt động và chưa hoàn tất hay không."""
        return self.get_service_state(zone_id) is ZoneServiceState.ACTIVE

    def has_open_dispatch(self, zone_id: str) -> bool:
        """Kiểm tra occupancy hiện tại đã từng tạo task phục vụ hay chưa."""
        return self.get_service_state(zone_id) is not ZoneServiceState.NOT_REQUESTED


# ─────────────────────────────────────────────────────────────────────────────
def _get_zone_id(zone: Zone) -> str:
    """Lấy định danh ổn định, ưu tiên id cấu hình và fallback về key của zone."""
    return str(zone.id or zone.key)
