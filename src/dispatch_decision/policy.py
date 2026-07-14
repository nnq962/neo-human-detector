"""Policy ánh xạ trạng thái zone thành hành động dispatch."""

from __future__ import annotations

from typing import Optional

from src.detection import Detection
from src.dispatch_decision.datatypes import DispatchAction, ZoneServiceState
from src.zones_management import ZoneState


# ─────────────────────────────────────────────────────────────────────────────
class ZoneOnlyDecisionPolicy:
    """Sinh action chỉ dựa trên transition và service state của zone."""

    def decide(
        self,
        previous_state: ZoneState,
        current_state: ZoneState,
        service_state: ZoneServiceState,
    ) -> Optional[DispatchAction]:
        """Trả action zone-only tương ứng, hoặc None nếu không cần xử lý."""
        if _should_cancel(
            previous_state=previous_state,
            current_state=current_state,
            service_state=service_state,
        ):
            return DispatchAction.TASK_CANCEL

        if (
            previous_state is ZoneState.PENDING_ENTER
            and current_state is ZoneState.OCCUPIED
            and service_state is ZoneServiceState.NOT_REQUESTED
        ):
            return DispatchAction.TASK_ASSIGN

        return None


# ─────────────────────────────────────────────────────────────────────────────
class ReIdDecisionPolicy:
    """Sinh action theo transition zone và danh tính người được chọn."""

    def decide(
        self,
        previous_state: ZoneState,
        current_state: ZoneState,
        service_state: ZoneServiceState,
        *,
        selected_person: Optional[Detection],
        person_service_blocked: bool,
        awaiting_identity: bool,
        awaiting_reassignment: bool,
        person_changed: bool,
        active_person_global_id: Optional[int],
    ) -> Optional[DispatchAction]:
        """Trả action ReID tương ứng, hoặc None nếu chưa đủ điều kiện."""
        if _should_cancel(
            previous_state=previous_state,
            current_state=current_state,
            service_state=service_state,
        ):
            return DispatchAction.TASK_CANCEL

        if (
            person_changed
            and active_person_global_id is not None
            and service_state is ZoneServiceState.REQUESTED
        ):
            return DispatchAction.TASK_CANCEL

        zone_ready = (
            previous_state is ZoneState.PENDING_ENTER
            and current_state is ZoneState.OCCUPIED
        ) or (
            awaiting_identity
            and current_state is ZoneState.OCCUPIED
        ) or (
            awaiting_reassignment
            and current_state is ZoneState.OCCUPIED
        ) or (
            person_changed
            and current_state is ZoneState.OCCUPIED
        )
        service_available = (
            service_state is ZoneServiceState.NOT_REQUESTED
            or (
                (person_changed or awaiting_reassignment)
                and service_state
                in {ZoneServiceState.COMPLETED, ZoneServiceState.FAILED}
            )
        )

        if (
            zone_ready
            and service_available
            and selected_person is not None
            and selected_person.global_id is not None
            and not person_service_blocked
        ):
            return DispatchAction.TASK_ASSIGN

        return None


# ─────────────────────────────────────────────────────────────────────────────
def _should_cancel(
    *,
    previous_state: ZoneState,
    current_state: ZoneState,
    service_state: ZoneServiceState,
) -> bool:
    """Kiểm tra service đang mở có cần hủy khi zone trở về EMPTY không."""
    return (
        previous_state is ZoneState.PENDING_EXIT
        and current_state is ZoneState.EMPTY
        and service_state is ZoneServiceState.REQUESTED
    )
