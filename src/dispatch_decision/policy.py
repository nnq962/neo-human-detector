"""Policy ánh xạ transition của zone thành hành động dispatch."""

from __future__ import annotations

from typing import Optional

from src.dispatch_decision.datatypes import DispatchAction, ZoneServiceState
from src.zones_management import ZoneState


# ─────────────────────────────────────────────────────────────────────────────
class ZoneOnlyDecisionPolicy:
    """Sinh action dựa trên trạng thái zone, chưa xét danh tính người."""

    def decide(
        self,
        previous_state: ZoneState,
        current_state: ZoneState,
        service_state: ZoneServiceState,
    ) -> Optional[DispatchAction]:
        """
        Trả action tương ứng với transition, hoặc None nếu không cần xử lý.

        Rule hiện tại:
        - PENDING_ENTER → OCCUPIED và chưa yêu cầu phục vụ: TASK_ASSIGN.
        - PENDING_EXIT → EMPTY và service đã được yêu cầu: TASK_CANCEL.
        - Các trường hợp còn lại: không sinh action.
        """
        if (
            previous_state is ZoneState.PENDING_ENTER
            and current_state is ZoneState.OCCUPIED
            and service_state is ZoneServiceState.NOT_REQUESTED
        ):
            return DispatchAction.TASK_ASSIGN

        if (
            previous_state is ZoneState.PENDING_EXIT
            and current_state is ZoneState.EMPTY
            and service_state is ZoneServiceState.REQUESTED
        ):
            return DispatchAction.TASK_CANCEL

        return None
