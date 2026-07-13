"""Điều phối việc đọc state, áp dụng policy và sinh dispatch decision."""

from __future__ import annotations

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
    """
    Sinh quyết định assign hoặc cancel từ transition trạng thái zone.

    Engine chỉ sinh ``DispatchDecision``. Việc chọn robot, cấp task_id và gửi
    message thuộc trách nhiệm của tầng thực thi robot.
    """

    def __init__(
        self,
        *,
        state_store: Optional[DispatchDecisionStateStore] = None,
        policy: Optional[ZoneOnlyDecisionPolicy] = None,
    ) -> None:
        """Khởi tạo engine với state store và policy mặc định."""
        self._state_store = state_store or DispatchDecisionStateStore()
        self._policy = policy or ZoneOnlyDecisionPolicy()
        self._lock = threading.RLock()

    # ─────────────────────────────────────────────────────────────────────
    def process_zones(self, zones: Sequence[Zone]) -> List[DispatchDecision]:
        """
        Xử lý trạng thái mới nhất của các zone và trả các decision phát sinh.

        Lần đầu quan sát một zone, engine chỉ lưu state ban đầu vì chưa có
        state trước đó để xác định transition.
        """
        decisions: List[DispatchDecision] = []

        with self._lock:
            for zone in zones:
                decision = self._process_zone(zone)

                if decision is not None:
                    decisions.append(decision)

        return decisions

    # ─────────────────────────────────────────────────────────────────────
    def _process_zone(self, zone: Zone) -> Optional[DispatchDecision]:
        """Xử lý một zone và trả decision nếu policy sinh action."""
        # Lấy định danh ổn định của zone.
        zone_id = _get_zone_id(zone)

        # Lấy trạng thái đã ghi nhận trong lần xử lý trước.
        stored_state = self._state_store.get(zone_id)

        # Zone mới chỉ được khởi tạo state vì chưa có transition để đánh giá.
        if stored_state is None:
            self._state_store.initialize(zone_id, zone.state)
            return None

        previous_state = stored_state.last_zone_state
        current_state = zone.state
        service_state = stored_state.service_state

        # Áp dụng policy lên transition và trạng thái phục vụ hiện tại.
        action = self._policy.decide(
            previous_state=previous_state,
            current_state=current_state,
            service_state=service_state,
        )

        # Luôn ghi nhận ZoneState mới nhất, kể cả khi không có decision.
        self._state_store.update_zone_state(zone_id, current_state)

        # Khi sinh TASK_ASSIGN, ghi nhận zone đã được yêu cầu phục vụ.
        if action is DispatchAction.TASK_ASSIGN:
            self._state_store.set_service_state(
                zone_id,
                ZoneServiceState.REQUESTED,
            )

        # Khi sinh TASK_CANCEL, đóng service của lượt occupancy hiện tại.
        elif action is DispatchAction.TASK_CANCEL:
            self._state_store.set_service_state(
                zone_id,
                ZoneServiceState.NOT_REQUESTED,
            )

        # Dọn service đã hoàn thành khi người rời khỏi zone.
        elif _should_reset_terminal_service(
            previous_state=previous_state,
            current_state=current_state,
            service_state=service_state,
        ):
            # Task đã kết thúc trước khi zone EMPTY nên không cần cancel.
            # Reset để lần occupancy tiếp theo có thể assign task mới.
            self._state_store.set_service_state(
                zone_id,
                ZoneServiceState.NOT_REQUESTED,
            )

        if action is None:
            return None

        return DispatchDecision(
            action=action,
            zone_id=zone_id,
            zone=zone,
            previous_state=previous_state,
            current_state=current_state,
        )

    # ─────────────────────────────────────────────────────────────────────
    def on_service_completed(self, zone_id: str) -> bool:
        """
        Đánh dấu task của zone đã hoàn thành.

        Trả True nếu zone đã được yêu cầu phục vụ và được cập nhật thành công.
        Trả False nếu zone không tồn tại hoặc chưa được yêu cầu phục vụ.
        """
        with self._lock:
            if (
                self._state_store.get_service_state(zone_id)
                is not ZoneServiceState.REQUESTED
            ):
                return False

            self._state_store.set_service_state(
                zone_id,
                ZoneServiceState.COMPLETED,
            )
            return True

    # ─────────────────────────────────────────────────────────────────────
    def on_service_failed(self, zone_id: str) -> bool:
        """
        Đánh dấu task của zone đã thất bại.

        Engine không tự sinh lại TASK_ASSIGN trong cùng lượt occupancy. Khi zone
        trở về EMPTY, state FAILED được reset để lượt sau có thể phục vụ lại.
        """
        with self._lock:
            if (
                self._state_store.get_service_state(zone_id)
                is not ZoneServiceState.REQUESTED
            ):
                return False

            self._state_store.set_service_state(
                zone_id,
                ZoneServiceState.FAILED,
            )
            return True

    # ─────────────────────────────────────────────────────────────────────
    def on_service_request_failed(self, zone_id: str) -> bool:
        """
        Rollback REQUESTED khi decision không thể chuyển thành yêu cầu hợp lệ.

        API này dành cho lỗi cục bộ không thể retry, ví dụ goal pose thiếu field.
        """
        with self._lock:
            if (
                self._state_store.get_service_state(zone_id)
                is not ZoneServiceState.REQUESTED
            ):
                return False

            self._state_store.set_service_state(
                zone_id,
                ZoneServiceState.NOT_REQUESTED,
            )
            return True

    # ─────────────────────────────────────────────────────────────────────
    def get_service_state(self, zone_id: str) -> ZoneServiceState:
        """Lấy trạng thái phục vụ hiện tại của zone."""
        with self._lock:
            return self._state_store.get_service_state(zone_id)

    # ─────────────────────────────────────────────────────────────────────
    def has_requested_service(self, zone_id: str) -> bool:
        """Trả True nếu zone đã sinh yêu cầu phục vụ và chưa hoàn thành."""
        return self.get_service_state(zone_id) is ZoneServiceState.REQUESTED

    # ─────────────────────────────────────────────────────────────────────
    def has_open_dispatch(self, zone_id: str) -> bool:
        """Trả True nếu occupancy hiện tại đã từng sinh TASK_ASSIGN."""
        return (
            self.get_service_state(zone_id)
            is not ZoneServiceState.NOT_REQUESTED
        )


# ─────────────────────────────────────────────────────────────────────────────
def _get_zone_id(zone: Zone) -> str:
    """Lấy định danh ổn định, ưu tiên id cấu hình và fallback về zone key."""
    return str(zone.id or zone.key)


# ─────────────────────────────────────────────────────────────────────────────
def _should_reset_terminal_service(
    *,
    previous_state: ZoneState,
    current_state: ZoneState,
    service_state: ZoneServiceState,
) -> bool:
    """True nếu service đã kết thúc và zone vừa trở về EMPTY."""
    return (
        previous_state is ZoneState.PENDING_EXIT
        and current_state is ZoneState.EMPTY
        and service_state
        in {ZoneServiceState.COMPLETED, ZoneServiceState.FAILED}
    )
