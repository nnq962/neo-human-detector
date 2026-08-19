"""Điều phối việc đọc state, áp dụng policy và sinh dispatch decision."""

from __future__ import annotations

import threading
from typing import List, Optional, Sequence

from src.detection import Detection
from src.dispatch_decision.datatypes import (
    DispatchAction,
    DispatchDecision,
    PersonServiceState,
    ZoneServiceState,
)
from src.dispatch_decision.person_selector import select_zone_person
from src.dispatch_decision.person_state_store import PersonServiceStateStore
from src.dispatch_decision.policy import (
    ReIdDecisionPolicy,
    ZoneOnlyDecisionPolicy,
)
from src.dispatch_decision.zone_state_store import ZoneDecisionStateStore
from src.zones_management import Zone, ZoneState
from utils import LOGGER


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
        zone_state_store: Optional[ZoneDecisionStateStore] = None,
        person_state_store: Optional[PersonServiceStateStore] = None,
        policy: Optional[ZoneOnlyDecisionPolicy | ReIdDecisionPolicy] = None,
    ) -> None:
        """Khởi tạo engine với state store và policy mặc định."""
        self._zone_state_store = zone_state_store or ZoneDecisionStateStore()
        self._person_state_store = person_state_store or PersonServiceStateStore()
        self._policy = policy or ZoneOnlyDecisionPolicy()
        self._use_reid = isinstance(self._policy, ReIdDecisionPolicy)
        self._lock = threading.RLock()

    # ────────────────────────────────────────────────────────────────────
    @property
    def uses_reid(self) -> bool:
        """Cho biết engine có đang dùng policy dựa trên global ID hay không."""
        return self._use_reid

    # ─────────────────────────────────────────────────────────────────────
    def process_zones(
        self,
        zones: Sequence[Zone],
        *,
        detections: Sequence[Detection] = (),
        zone_names: Sequence[Optional[str]] = (),
    ) -> List[DispatchDecision]:
        """
        Xử lý trạng thái mới nhất của các zone và trả các decision phát sinh.

        ``detections`` và ``zone_names`` dùng chung thứ tự để chọn người trong
        từng zone khi policy bật ReID. Lần đầu quan sát một zone, engine chỉ lưu
        state ban đầu vì chưa có state trước đó để xác định transition.
        """
        decisions: List[DispatchDecision] = []

        with self._lock:
            for zone in zones:
                if self._use_reid:
                    decision = self._process_zone_with_reid(
                        zone,
                        detections=detections,
                        zone_names=zone_names,
                    )
                else:
                    decision = self._process_zone_only(zone)

                if decision is not None:
                    decisions.append(decision)

        return decisions

    # ─────────────────────────────────────────────────────────────────────
    def _process_zone_only(self, zone: Zone) -> Optional[DispatchDecision]:
        """Xử lý một zone chỉ bằng transition, không dùng dữ liệu ReID."""
        # Lấy định danh ổn định và state đã ghi nhận ở lần xử lý trước.
        zone_id = _get_zone_id(zone)
        stored_state = self._zone_state_store.get(zone_id)

        # Lần đầu chỉ khởi tạo vì chưa có state trước đó để xét transition.
        if stored_state is None:
            self._zone_state_store.initialize(zone_id, zone.state)
            return None

        # Chụp state trước/sau và trạng thái service để đưa vào policy zone-only.
        previous_state = stored_state.last_zone_state
        current_state = zone.state
        service_state = stored_state.service_state

        # Áp dụng policy lên transition và trạng thái phục vụ hiện tại.
        action = self._policy.decide(
            previous_state=previous_state,
            current_state=current_state,
            service_state=service_state,
        )

        # Tính service state mới rồi commit cùng ZoneState trong một lần update.
        next_service_state = service_state
        if action is DispatchAction.TASK_ASSIGN:
            next_service_state = ZoneServiceState.REQUESTED
        elif action is DispatchAction.TASK_CANCEL:
            next_service_state = ZoneServiceState.CANCEL_REQUESTED
        elif _should_reset_terminal_service(
            previous_state=previous_state,
            current_state=current_state,
            service_state=service_state,
        ):
            next_service_state = ZoneServiceState.NOT_REQUESTED

        # Luôn lưu state mới nhất, kể cả khi policy không sinh action.
        self._zone_state_store.update(
            zone_id,
            last_zone_state=current_state,
            service_state=next_service_state,
        )

        # Không có action nghĩa là engine chỉ cập nhật state, không tạo decision.
        if action is None:
            return None

        # Decision zone-only không mang theo bất kỳ thông tin người nào.
        return DispatchDecision(
            action=action,
            zone_id=zone_id,
            zone=zone,
            previous_state=previous_state,
            current_state=current_state,
            priority=zone.priority,
        )

    # ─────────────────────────────────────────────────────────────────────
    def _process_zone_with_reid(
        self,
        zone: Zone,
        *,
        detections: Sequence[Detection],
        zone_names: Sequence[Optional[str]],
    ) -> Optional[DispatchDecision]:
        """Xử lý một zone bằng identity và trạng thái phục vụ toàn cục."""
        # Lấy định danh ổn định và state đã ghi nhận ở lần xử lý trước.
        zone_id = _get_zone_id(zone)
        stored_state = self._zone_state_store.get(zone_id)

        # Lần đầu chỉ khởi tạo vì chưa có state trước đó để xét transition.
        if stored_state is None:
            self._zone_state_store.initialize(zone_id, zone.state)
            return None

        # Chụp toàn bộ state cần thiết trước khi policy đưa ra quyết định.
        previous_state = stored_state.last_zone_state
        current_state = zone.state
        service_state = stored_state.service_state

        # Chọn người đã có global ID và similarity cao nhất trong zone.
        selected_person = select_zone_person(
            zone,
            detections,
            zone_names,
        )
        selected_person_global_id = (
            None if selected_person is None else selected_person.global_id
        )
        previous_person_global_id = (
            stored_state.observed_person_global_id
            if stored_state.observed_person_global_id is not None
            else stored_state.active_person_global_id
        )
        person_changed = (
            selected_person_global_id is not None
            and previous_person_global_id is not None
            and selected_person_global_id != previous_person_global_id
        )
        # REQUESTED và SERVED đều chặn cùng người nhận thêm task ở mọi zone.
        person_service_blocked = (
            selected_person_global_id is not None
            and self._person_state_store.is_blocked(selected_person_global_id)
        )

        # Policy kết hợp transition, trạng thái chờ ID và trạng thái của người.
        action = self._policy.decide(
            previous_state=previous_state,
            current_state=current_state,
            service_state=service_state,
            selected_person=selected_person,
            person_service_blocked=person_service_blocked,
            awaiting_identity=stored_state.awaiting_identity,
            awaiting_reassignment=stored_state.awaiting_reassignment,
            person_changed=person_changed,
            active_person_global_id=stored_state.active_person_global_id,
        )

        # Cancel cần dùng lại active global ID vì lúc đó zone có thể hết detection.
        decision_person_global_id = stored_state.active_person_global_id
        decision_person_similarity: Optional[float] = None
        decision_person_track_id: Optional[int] = None

        # Giữ chỗ global ID trước khi commit assign để tránh task trùng xuyên zone.
        if action is DispatchAction.TASK_ASSIGN:
            if selected_person is None or selected_person.global_id is None:
                action = None
            elif not self._person_state_store.mark_requested(
                selected_person.global_id,
                zone_id,
            ):
                action = None
            else:
                decision_person_global_id = selected_person.global_id
                decision_person_similarity = selected_person.similarity
                decision_person_track_id = selected_person.track_id

        # Tính state kế tiếp trước khi commit nguyên khối vào zone store.
        next_service_state = service_state
        next_awaiting_identity = stored_state.awaiting_identity
        next_awaiting_reassignment = stored_state.awaiting_reassignment
        next_observed_person_global_id = stored_state.observed_person_global_id
        next_active_person_global_id = stored_state.active_person_global_id

        if selected_person_global_id is not None:
            next_observed_person_global_id = selected_person_global_id

        if action is DispatchAction.TASK_ASSIGN:
            next_service_state = ZoneServiceState.REQUESTED
            next_awaiting_identity = False
            next_awaiting_reassignment = False
            next_active_person_global_id = decision_person_global_id
        elif action is DispatchAction.TASK_CANCEL:
            # Giữ person REQUESTED cho tới khi tầng thực thi xác nhận cancel xong.
            next_service_state = ZoneServiceState.CANCEL_REQUESTED
            if person_changed and current_state is ZoneState.OCCUPIED:
                next_awaiting_reassignment = True
        elif _should_reset_terminal_service(
            previous_state=previous_state,
            current_state=current_state,
            service_state=service_state,
        ):
            next_service_state = ZoneServiceState.NOT_REQUESTED
            next_active_person_global_id = None

        # Awaiting identity sống qua OCCUPIED ↔ PENDING_EXIT và dừng khi EMPTY.
        if current_state is ZoneState.EMPTY:
            next_awaiting_identity = False
            next_awaiting_reassignment = False
            next_observed_person_global_id = None
        elif (
            previous_state is ZoneState.PENDING_ENTER
            and current_state is ZoneState.OCCUPIED
            and service_state is ZoneServiceState.NOT_REQUESTED
            and action is not DispatchAction.TASK_ASSIGN
            and selected_person_global_id is None
        ):
            next_awaiting_identity = True

        # Commit tất cả field cùng lúc để không lộ state trung gian.
        self._zone_state_store.update(
            zone_id,
            last_zone_state=current_state,
            service_state=next_service_state,
            awaiting_identity=next_awaiting_identity,
            awaiting_reassignment=next_awaiting_reassignment,
            observed_person_global_id=next_observed_person_global_id,
            active_person_global_id=next_active_person_global_id,
        )

        # Không có action nghĩa là engine chỉ cập nhật các state nội bộ.
        if action is None:
            return None

        # Decision ReID mang identity để tầng thực thi liên kết task với người.
        return DispatchDecision(
            action=action,
            zone_id=zone_id,
            zone=zone,
            previous_state=previous_state,
            current_state=current_state,
            priority=zone.priority,
            person_global_id=decision_person_global_id,
            person_similarity=decision_person_similarity,
            person_track_id=decision_person_track_id,
        )

    # ─────────────────────────────────────────────────────────────────────
    def on_service_completed(self, zone_id: str) -> bool:
        """
        Đánh dấu task của zone đã hoàn thành.

        Trả True nếu zone đã được yêu cầu phục vụ và được cập nhật thành công.
        Trả False nếu zone không tồn tại hoặc chưa được yêu cầu phục vụ.
        """
        with self._lock:
            service_state = self._zone_state_store.get_service_state(zone_id)
            if service_state not in {
                ZoneServiceState.REQUESTED,
                ZoneServiceState.CANCEL_REQUESTED,
            }:
                return False

            self._zone_state_store.update(
                zone_id,
                service_state=ZoneServiceState.COMPLETED,
            )
            global_id = self._zone_state_store.get_active_person_global_id(zone_id)
            if (
                global_id is not None
                and not self._person_state_store.mark_served(global_id, zone_id)
            ):
                LOGGER.warning(
                    "Không thể đánh dấu người đã phục vụ: "
                    "zone_id=%s, global_id=%s",
                    zone_id,
                    global_id,
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
            service_state = self._zone_state_store.get_service_state(zone_id)
            if service_state not in {
                ZoneServiceState.REQUESTED,
                ZoneServiceState.CANCEL_REQUESTED,
            }:
                return False

            self._release_active_person_request(zone_id)
            self._zone_state_store.update(
                zone_id,
                service_state=ZoneServiceState.FAILED,
                active_person_global_id=None,
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
                self._zone_state_store.get_service_state(zone_id)
                is not ZoneServiceState.REQUESTED
            ):
                return False

            self._release_active_person_request(zone_id)
            self._zone_state_store.update(
                zone_id,
                service_state=ZoneServiceState.NOT_REQUESTED,
                active_person_global_id=None,
            )
            return True

    # ─────────────────────────────────────────────────────────────────────
    def request_service_cancel(self, zone_id: str) -> bool:
        """Chuyển service đang hoạt động sang trạng thái chờ hủy chủ động."""
        with self._lock:
            service_state = self._zone_state_store.get_service_state(zone_id)
            if service_state is ZoneServiceState.CANCEL_REQUESTED:
                return True
            if service_state is not ZoneServiceState.REQUESTED:
                return False
            self._zone_state_store.update(
                zone_id,
                service_state=ZoneServiceState.CANCEL_REQUESTED,
            )
            return True

    # ─────────────────────────────────────────────────────────────────────
    def on_service_cancelled(self, zone_id: str) -> bool:
        """Đóng service sau khi tầng thực thi xác nhận TaskCancel hoàn tất."""
        with self._lock:
            if (
                self._zone_state_store.get_service_state(zone_id)
                is not ZoneServiceState.CANCEL_REQUESTED
            ):
                return False

            self._release_active_person_request(zone_id)
            self._zone_state_store.update(
                zone_id,
                service_state=ZoneServiceState.NOT_REQUESTED,
                active_person_global_id=None,
            )
            return True

    # ─────────────────────────────────────────────────────────────────────
    def get_service_state(self, zone_id: str) -> ZoneServiceState:
        """Lấy trạng thái phục vụ hiện tại của zone."""
        with self._lock:
            return self._zone_state_store.get_service_state(zone_id)

    # ─────────────────────────────────────────────────────────────────────
    def has_requested_service(self, zone_id: str) -> bool:
        """Trả True nếu zone đã sinh yêu cầu phục vụ và chưa hoàn thành."""
        return self.get_service_state(zone_id) in {
            ZoneServiceState.REQUESTED,
            ZoneServiceState.CANCEL_REQUESTED,
        }

    # ─────────────────────────────────────────────────────────────────────
    def has_open_dispatch(self, zone_id: str) -> bool:
        """Trả True nếu occupancy hiện tại đã từng sinh TASK_ASSIGN."""
        return (
            self.get_service_state(zone_id)
            is not ZoneServiceState.NOT_REQUESTED
        )

    # ─────────────────────────────────────────────────────────────────────
    def is_awaiting_identity(self, zone_id: str) -> bool:
        """Trả True nếu zone đang chờ ReID xác nhận danh tính người."""
        with self._lock:
            return self._zone_state_store.is_awaiting_identity(zone_id)

    # ─────────────────────────────────────────────────────────────────────
    def is_awaiting_reassignment(self, zone_id: str) -> bool:
        """Trả True nếu zone đang chờ assign cho người thay thế."""
        with self._lock:
            return self._zone_state_store.is_awaiting_reassignment(zone_id)

    # ─────────────────────────────────────────────────────────────────────
    def get_person_service_state(
        self,
        global_id: int,
    ) -> Optional[PersonServiceState]:
        """Lấy trạng thái phục vụ toàn cục của một người."""
        with self._lock:
            return self._person_state_store.get_state(global_id)

    # ─────────────────────────────────────────────────────────────────────
    def has_person_been_served(self, global_id: int) -> bool:
        """Trả True nếu người đã được robot báo phục vụ hoàn thành."""
        return (
            self.get_person_service_state(global_id)
            is PersonServiceState.SERVED
        )

    # ─────────────────────────────────────────────────────────────────────
    def _release_active_person_request(self, zone_id: str) -> None:
        """Giải phóng request chưa hoàn thành của người gắn với zone."""
        global_id = self._zone_state_store.get_active_person_global_id(zone_id)
        if global_id is not None:
            self._person_state_store.release_request(global_id, zone_id)

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
