"""Policy ánh xạ transition zone thành action điều phối robot."""

from typing import Optional

from src.dispatch_decision.datatypes import DispatchAction, ZoneServiceState
from src.zones_management import ZoneState


# ─────────────────────────────────────────────────────────────────────────────
class ZoneOnlyDecisionPolicy:
    """Chỉ sinh action từ hai transition đã được xác nhận bởi vision."""

    def decide(
        self,
        previous_state: ZoneState,
        current_state: ZoneState,
        service_state: ZoneServiceState,
    ) -> Optional[DispatchAction]:
        """Trả action hợp lệ cho transition, hoặc ``None`` nếu không cần lệnh."""
        if (
            previous_state is ZoneState.PENDING_ENTER
            and current_state is ZoneState.OCCUPIED
            and service_state is ZoneServiceState.NOT_REQUESTED
        ):
            return DispatchAction.TASK_ASSIGN

        if (
            previous_state is ZoneState.PENDING_EXIT
            and current_state is ZoneState.EMPTY
            and service_state is ZoneServiceState.ACTIVE
        ):
            return DispatchAction.TASK_CANCEL

        return None
