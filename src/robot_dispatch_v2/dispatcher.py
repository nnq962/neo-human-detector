"""Thực thi các quyết định dispatch bằng giao thức robot nhị phân V2."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, replace
from typing import List, Optional, Protocol, Sequence

from src.detection import Detection
from src.dispatch_decision import (
    DispatchAction,
    DispatchDecision,
    DispatchDecisionEngine,
)
from src.robot_dispatch_v2.datatypes import (
    Ack,
    AckReasonCode,
    AckResultCode,
    Heartbeat,
    MessageBase,
    MessageType,
    TaskAssign,
    TaskCancel,
    TaskStatus,
    TaskStatusCode,
)
from src.robot_dispatch_v2.robot_state import RobotStateStore
from src.robot_dispatch_v2.task_registry import (
    AssignedTask,
    TaskRegistry,
    TaskRegistryFull,
)
from src.robot_dispatch_v2.task_activity import TaskActivityStore, TaskPriority
from src.zones_management import Zone
from utils import LOGGER


DEFAULT_ACK_TIMEOUT_SECONDS = 1.0
DEFAULT_MAX_RETRIES = 5
BACKGROUND_DISPATCH_INTERVAL_SECONDS = 0.25
TASK_PRIORITY_RANK = {
    TaskPriority.LOW: 1,
    TaskPriority.MEDIUM: 2,
    TaskPriority.HIGH: 3,
}


# ─────────────────────────────────────────────────────────────────────────────
def _ack_reason_name(reason_code: int) -> str:
    """Đổi mã nguyên nhân ACK sang tên dễ đọc trong log dispatcher."""
    try:
        return AckReasonCode(reason_code).name
    except ValueError:
        return "UNKNOWN"


# ─────────────────────────────────────────────────────────────────────────────
class UartTransport(Protocol):
    """Phần API UART mà RobotDispatcherV2 cần sử dụng."""

    def set_handler(self, message_type: int, handler) -> None:
        """Đăng ký handler cho một loại message."""

    def add_handler(self, message_type: int, handler) -> None:
        """Thêm handler mà không ghi đè handler hiện có."""

    def send_message(self, message: MessageBase) -> bool:
        """Gửi một message đúng một lần."""

    def send_with_retry_ack(
        self,
        message: MessageBase,
        reference_id: int,
        timeout: float = 1.0,
        max_retries: int = 5,
    ) -> Optional[Ack]:
        """Gửi message và trả ACK đầy đủ, hoặc ``None`` nếu hết thời gian."""


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class _PendingAssignment:
    """Snapshot bất biến của một yêu cầu assign đang chờ thực thi."""

    task_uid: str
    x: float
    y: float
    theta: float
    priority: TaskPriority
    enqueue_sequence: int = 0
    robot_id: Optional[int] = None
    task_id: Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
class RobotDispatcherV2:
    """
    Chuyển ``DispatchDecision`` thành lệnh gửi tới robot.

    Trách nhiệm chính:
    - Cập nhật vị trí/trạng thái robot từ Heartbeat.
    - Chọn robot IDLE gần goal pose nhất.
    - Cấp và giải phóng task_id qua TaskRegistry.
    - Gửi TaskAssign/TaskCancel với cơ chế chờ ACK và retry.
    - Xử lý TaskStatus, gửi ACK và báo hoàn thành cho decision engine.
    - Giữ decision chưa thực thi được để ``tick()`` thử lại sau.
    """

    def __init__(
        self,
        uart: UartTransport,
        *,
        decision_engine: Optional[DispatchDecisionEngine] = None,
        robot_state_store: Optional[RobotStateStore] = None,
        task_registry: Optional[TaskRegistry] = None,
        task_activity_store: Optional[TaskActivityStore] = None,
        ack_timeout_seconds: float = DEFAULT_ACK_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        register_handlers: bool = True,
        register_heartbeat_handler: bool = True,
        background_ack: bool = False,
    ) -> None:
        """Khởi tạo dispatcher và tùy chọn đăng ký các UART handler cần thiết."""
        self._uart = uart
        self._decision_engine = decision_engine or DispatchDecisionEngine()
        self._robot_state_store = robot_state_store or RobotStateStore()
        self._task_registry = task_registry or TaskRegistry()
        self._task_activity_store = task_activity_store or TaskActivityStore()
        self._ack_timeout_seconds = ack_timeout_seconds
        self._max_retries = max_retries
        self._register_heartbeat_handler = register_heartbeat_handler
        self._background_ack = background_ack

        self._pending_assignments: dict[str, _PendingAssignment] = {}
        self._pending_cancellations: set[str] = set()
        self._enqueue_sequence = 0
        self._lock = threading.RLock()
        self._background_stop = threading.Event()
        self._background_wakeup = threading.Event()
        self._background_thread: Optional[threading.Thread] = None
        self._handlers_registered = False
        self._registered_with_add_handler = False

        if register_handlers:
            self.register_uart_handlers()
        if self._background_ack:
            self._start_background_worker()

    # ─────────────────────────────────────────────────────────────────────────
    @property
    def decision_engine(self) -> DispatchDecisionEngine:
        """Decision engine đang được dispatcher dùng để nhận feedback task."""
        return self._decision_engine

    # ─────────────────────────────────────────────────────────────────────────
    @property
    def robot_state_store(self) -> RobotStateStore:
        """Kho snapshot robot được cập nhật từ Heartbeat."""
        return self._robot_state_store

    @property
    def task_activity_store(self) -> TaskActivityStore:
        """Read-model task được cập nhật theo lifecycle thực thi."""
        return self._task_activity_store

    # ─────────────────────────────────────────────────────────────────────────
    def register_uart_handlers(self) -> None:
        """Đăng ký subscriber Heartbeat và TaskStatus, không đăng ký trùng."""
        with self._lock:
            if self._handlers_registered:
                return

            add_handler = getattr(self._uart, "add_handler", None)
            if callable(add_handler):
                if self._register_heartbeat_handler:
                    add_handler(MessageType.HEARTBEAT, self.on_heartbeat)
                add_handler(MessageType.TASK_STATUS, self.on_task_status)
                self._registered_with_add_handler = True
            else:
                # Fallback cho transport tối giản chỉ triển khai set_handler().
                if self._register_heartbeat_handler:
                    self._uart.set_handler(MessageType.HEARTBEAT, self.on_heartbeat)
                self._uart.set_handler(MessageType.TASK_STATUS, self.on_task_status)
                self._registered_with_add_handler = False

            self._handlers_registered = True

    # ─────────────────────────────────────────────────────────────────────
    def close(self) -> None:
        """
        Gỡ các UART handler do dispatcher đăng ký.

        Dispatcher không đóng UART transport vì vòng đời kết nối thuộc về bên
        đã truyền transport vào constructor, thường là Runtime.
        """
        self._stop_background_worker()

        with self._lock:
            if not self._handlers_registered:
                return

            registered_with_add_handler = self._registered_with_add_handler
            self._handlers_registered = False
            self._registered_with_add_handler = False

        if registered_with_add_handler:
            remove_handler = getattr(self._uart, "remove_handler", None)
            if callable(remove_handler):
                if self._register_heartbeat_handler:
                    remove_handler(MessageType.HEARTBEAT, self.on_heartbeat)
                remove_handler(MessageType.TASK_STATUS, self.on_task_status)
                return

        # Fallback cho transport không có API subscriber. Trong trường hợp này
        # register_uart_handlers() đã dùng set_handler(), nên dispatcher sở hữu
        # hai handler chính và có thể gỡ chúng bằng cách truyền None.
        if self._register_heartbeat_handler:
            self._uart.set_handler(MessageType.HEARTBEAT, None)
        self._uart.set_handler(MessageType.TASK_STATUS, None)

    # ─────────────────────────────────────────────────────────────────────────
    def process_zones(
        self,
        zones: Sequence[Zone],
        *,
        detections: Sequence[Detection] = (),
        zone_names: Sequence[Optional[str]] = (),
    ) -> List[DispatchDecision]:
        """
        Sinh decision từ các zone rồi thực thi từng decision.

        Giá trị trả về là danh sách decision đã được engine sinh ra. Một decision
        chưa thực thi được ngay vẫn được giữ lại để ``tick()`` thử lại.
        """
        decisions = self._decision_engine.process_zones(
            zones,
            detections=detections,
            zone_names=zone_names,
        )
        self.process_decisions(decisions)
        return decisions

    # ─────────────────────────────────────────────────────────────────────────
    def process_decisions(
        self,
        decisions: Sequence[DispatchDecision],
    ) -> List[bool]:
        """Thực thi cancel trước, rồi assign theo priority và giữ thứ tự trả về."""
        indexed_decisions = list(enumerate(decisions))
        ordered_decisions = sorted(
            indexed_decisions,
            key=lambda item: _decision_dispatch_sort_key(item[1]),
        )
        results = [False] * len(indexed_decisions)
        for original_index, decision in ordered_decisions:
            results[original_index] = self.process_decision(decision)
        return results

    # ─────────────────────────────────────────────────────────────────────────
    def process_decision(self, decision: DispatchDecision) -> bool:
        """
        Thực thi một decision.

        Trả True nếu decision đã được xử lý xong ngay. Trả False nếu lệnh chưa
        thực thi được và đã được giữ lại để ``tick()`` thử lại.
        """
        if decision.action is DispatchAction.TASK_ASSIGN:
            pending = _build_pending_assignment(decision)
            if pending is None:
                self._decision_engine.on_service_request_failed(decision.zone_id)
                return False

            try:
                task_priority = TaskPriority(decision.priority.value)
                task_uid = self._task_activity_store.create_task(
                    camera_id=decision.zone.camera_id,
                    camera_name=decision.zone.camera_name,
                    origin="zone",
                    priority=task_priority,
                    target_pixel=decision.zone.service_point,
                    goal_pose={
                        "x": pending.x,
                        "y": pending.y,
                        "theta": pending.theta,
                    },
                    zone_id=decision.zone_id,
                    zone_name=decision.zone.name,
                    person_global_id=decision.person_global_id,
                    person_similarity=decision.person_similarity,
                    person_track_id=decision.person_track_id,
                )
            except ValueError as exc:
                LOGGER.warning("Không thể tạo task cho zone %s: %s", decision.zone_id, exc)
                self._decision_engine.on_service_request_failed(decision.zone_id)
                return False

            return self._enqueue_assignment(
                replace(
                    pending,
                    task_uid=task_uid,
                    priority=task_priority,
                    enqueue_sequence=self._next_enqueue_sequence(),
                )
            )

        if decision.action is DispatchAction.TASK_CANCEL:
            task_uid = self._task_activity_store.get_active_uid_by_zone(
                decision.zone_id
            )
            if task_uid is None:
                self._decision_engine.on_service_cancelled(decision.zone_id)
                return True
            return self._request_cancel(task_uid, update_decision_engine=False)

        LOGGER.warning("Bỏ qua dispatch action không được hỗ trợ: %s", decision.action)
        return False

    # ─────────────────────────────────────────────────────────────────────────
    def enqueue_manual_task(
        self,
        *,
        camera_id: str,
        camera_name: str,
        target_pixel: tuple[float, float],
        goal_pose: dict[str, float],
        priority: TaskPriority,
    ) -> str:
        """Thêm task do người dùng tạo vào cùng hàng đợi priority của zone."""
        x, y, theta = _parse_goal_pose(goal_pose)
        task_uid = self._task_activity_store.create_task(
            camera_id=camera_id,
            camera_name=camera_name,
            origin="manual",
            priority=priority,
            target_pixel=target_pixel,
            goal_pose={"x": x, "y": y, "theta": theta},
        )
        self._enqueue_assignment(
            _PendingAssignment(
                task_uid=task_uid,
                x=x,
                y=y,
                theta=theta,
                priority=priority,
                enqueue_sequence=self._next_enqueue_sequence(),
            )
        )
        return task_uid

    # ─────────────────────────────────────────────────────────────────────────
    def cancel_task(self, task_uid: str) -> bool:
        """Yêu cầu hủy một task từ bất kỳ nguồn nào theo UID runtime."""
        task = self._task_activity_store.get(task_uid)
        if task is None:
            raise KeyError(f"Không tìm thấy task {task_uid}")
        if task.status == "CANCELED":
            return True
        if task.status in {"COMPLETED", "FAILED"}:
            raise ValueError(
                f"Task {task_uid} đã kết thúc với trạng thái {task.status}"
            )
        return self._request_cancel(task_uid, update_decision_engine=True)

    # ─────────────────────────────────────────────────────────────────────────
    def change_task_priority(
        self,
        task_uid: str,
        priority: TaskPriority,
    ) -> bool:
        """Đổi priority của task chưa bắt đầu assign và sắp xếp lại hàng đợi."""
        with self._lock:
            pending = self._pending_assignments.get(task_uid)
            if pending is None or pending.robot_id is not None:
                return False
        if not self._task_activity_store.change_priority(task_uid, priority):
            return False
        with self._lock:
            pending = self._pending_assignments.get(task_uid)
            if pending is None or pending.robot_id is not None:
                return False
            self._pending_assignments[task_uid] = replace(
                pending,
                priority=priority,
            )
        self._schedule_background_dispatch()
        return True

    # ─────────────────────────────────────────────────────────────────────────
    def _enqueue_assignment(self, pending: _PendingAssignment) -> bool:
        """Đưa assignment vào hàng đợi UID và thử gửi theo chế độ dispatcher."""
        with self._lock:
            self._pending_assignments[pending.task_uid] = pending
        if self._background_ack:
            self._schedule_background_dispatch()
            return False
        return self._try_assign(pending)

    # ─────────────────────────────────────────────────────────────────────────
    def _request_cancel(
        self,
        task_uid: str,
        *,
        update_decision_engine: bool,
    ) -> bool:
        """Ghi nhận cancel theo UID và ưu tiên xử lý trước assignment."""
        task = self._task_activity_store.get(task_uid)
        if task is None:
            raise KeyError(f"Không tìm thấy task {task_uid}")
        if task.status == "CANCELED":
            return True

        if update_decision_engine and task.origin == "zone" and task.zone_id:
            if not self._decision_engine.request_service_cancel(task.zone_id):
                raise ValueError(
                    f"Zone {task.zone_id} không có service có thể hủy"
                )

        self._task_activity_store.mark_cancel_requested(task_uid)
        with self._lock:
            self._pending_assignments.pop(task_uid, None)
            self._pending_cancellations.add(task_uid)

        if self._background_ack:
            self._schedule_background_dispatch()
            return False
        return self._try_cancel(task_uid)

    # ─────────────────────────────────────────────────────────────────────────
    def tick(self) -> int:
        """
        Thử lại các decision chưa thực thi được.

        Cancel luôn được thử trước assign để tránh giao task mới trong khi task
        cũ của một zone vẫn chưa hủy xong. Trả số decision hoàn tất trong tick.
        """
        if self._background_ack:
            self._schedule_background_dispatch()
            return 0
        return self._run_pending_once()

    # ─────────────────────────────────────────────────────────────────────────
    def _run_pending_once(self) -> int:
        """Thử một lượt cancel rồi assign cho các decision đang chờ."""
        with self._lock:
            cancellation_task_uids = list(self._pending_cancellations)
            assignments = list(self._pending_assignments.values())

        assignments.sort(key=_pending_assignment_sort_key)

        completed_count = 0

        for task_uid in cancellation_task_uids:
            if self._try_cancel(task_uid):
                completed_count += 1

        for pending in assignments:
            with self._lock:
                if pending.task_uid in self._pending_cancellations:
                    continue
                if self._pending_assignments.get(pending.task_uid) != pending:
                    continue

            if self._try_assign(pending):
                completed_count += 1

        return completed_count

    # ─────────────────────────────────────────────────────────────────────────
    def _start_background_worker(self) -> None:
        """Khởi động worker chuyên chờ ACK để không chặn thread Runtime."""
        with self._lock:
            if self._background_thread is not None:
                return
            self._background_stop.clear()
            self._background_thread = threading.Thread(
                target=self._background_loop,
                name="robot-dispatch-ack",
                daemon=True,
            )
            self._background_thread.start()

    # ─────────────────────────────────────────────────────────────────────────
    def _next_enqueue_sequence(self) -> int:
        """Cấp số thứ tự tăng dần để giữ FIFO giữa task cùng priority."""
        with self._lock:
            sequence = self._enqueue_sequence
            self._enqueue_sequence += 1
            return sequence

    # ─────────────────────────────────────────────────────────────────────────
    def _stop_background_worker(self) -> None:
        """Yêu cầu worker dừng và chờ ngắn trước khi gỡ UART handler."""
        if not self._background_ack:
            return
        self._background_stop.set()
        self._background_wakeup.set()

        with self._lock:
            thread = self._background_thread
            self._background_thread = None

        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    # ─────────────────────────────────────────────────────────────────────────
    def _schedule_background_dispatch(self) -> None:
        """Đánh thức worker để xử lý decision đang chờ sớm nhất có thể."""
        self._background_wakeup.set()

    # ─────────────────────────────────────────────────────────────────────────
    def _background_loop(self) -> None:
        """Xử lý ACK/retry nền tuần tự, ưu tiên cancel như đường đồng bộ cũ."""
        while not self._background_stop.is_set():
            self._background_wakeup.wait(BACKGROUND_DISPATCH_INTERVAL_SECONDS)
            self._background_wakeup.clear()
            if self._background_stop.is_set():
                return
            self._run_pending_once()

    # ─────────────────────────────────────────────────────────────────────────
    def on_heartbeat(self, message: Heartbeat) -> None:
        """Cập nhật snapshot robot từ Heartbeat mới nhận được."""
        self._robot_state_store.update_from_heartbeat(message)

    # ─────────────────────────────────────────────────────────────────────────
    def on_task_status(self, message: TaskStatus) -> None:
        """
        Xử lý trạng thái task và gửi ACK đúng một lần.

        Robot có thể gửi lại cùng một status nếu ACK bị mất. Vì vậy handler phải
        chấp nhận message lặp và vẫn gửi lại ACK mà không tạo side effect lặp.
        """
        task = self._task_registry.get(message.robot_id, message.task_id)

        try:
            status = TaskStatusCode(message.status_code)
        except ValueError:
            LOGGER.warning(
                "Bỏ qua TaskStatus có status_code không hợp lệ: "
                "robot_id=%s, task_id=%s, status_code=%s",
                message.robot_id,
                message.task_id,
                message.status_code,
            )
            self._send_task_status_ack(message)
            return

        if task is None:
            # Có thể là bản gửi lại của terminal status đã xử lý trước đó.
            LOGGER.info(
                "Nhận TaskStatus cho task không còn trong registry: "
                "robot_id=%s, task_id=%s, status=%s",
                message.robot_id,
                message.task_id,
                status.name,
            )
            self._send_task_status_ack(message)
            return

        # Có TaskStatus nghĩa là robot đã nhận task, kể cả khi ACK TaskAssign
        # trước đó bị mất trên đường truyền.
        self._remove_pending_assignment(task.task_uid)

        if status is TaskStatusCode.COMPLETED:
            task_activity = self._task_activity_store.get(task.task_uid)
            self._task_activity_store.mark_completed(task.task_uid)
            self._task_registry.release(message.robot_id, message.task_id)
            self._remove_pending_cancellation(task.task_uid)
            if (
                task_activity is not None
                and task_activity.origin == "zone"
                and task_activity.zone_id is not None
            ):
                self._decision_engine.on_service_completed(task_activity.zone_id)

        elif status is TaskStatusCode.FAILED:
            task_activity = self._task_activity_store.get(task.task_uid)
            self._task_activity_store.mark_failed(task.task_uid)
            # Không tự giao lại task vì retry nghiệp vụ cần policy riêng.
            self._task_registry.release(message.robot_id, message.task_id)
            self._remove_pending_cancellation(task.task_uid)
            if (
                task_activity is not None
                and task_activity.origin == "zone"
                and task_activity.zone_id is not None
            ):
                self._decision_engine.on_service_failed(task_activity.zone_id)
            LOGGER.warning(
                "Task thất bại: robot_id=%s, task_id=%s, task_uid=%s",
                message.robot_id,
                message.task_id,
                task.task_uid,
            )

        elif status is TaskStatusCode.IN_PROGRESS:
            self._task_activity_store.mark_in_progress(task.task_uid)

        self._send_task_status_ack(message)

    # ─────────────────────────────────────────────────────────────────────────
    def get_assigned_task_by_uid(
        self,
        task_uid: str,
    ) -> Optional[AssignedTask]:
        """Lấy reservation robot hiện tại theo UID runtime."""
        return self._task_registry.get_by_uid(task_uid)

    # ─────────────────────────────────────────────────────────────────────────
    def pending_count(self) -> int:
        """Trả tổng số assign/cancel đang chờ thử lại."""
        with self._lock:
            return len(self._pending_assignments) + len(self._pending_cancellations)

    # ─────────────────────────────────────────────────────────────────────────
    def _try_assign(self, pending: _PendingAssignment) -> bool:
        """Thử chọn robot, cấp task và gửi TaskAssign cho một yêu cầu đang chờ."""
        task = self._task_registry.get_by_uid(pending.task_uid)

        if task is None:
            # Registry từng có task nhưng nay không còn nghĩa là terminal status
            # đã xử lý task trong lúc một lần gửi đang chờ ACK.
            if pending.robot_id is not None and pending.task_id is not None:
                self._remove_pending_assignment(pending.task_uid)
                return True

            robot = self._robot_state_store.nearest_idle_robot(
                pending.x,
                pending.y,
                excluded_robot_ids=self._task_registry.reserved_robot_ids(),
            )
            if robot is None:
                # LOGGER.info(
                #     "Chưa có robot IDLE cho task %s; giữ lại để thử sau.",
                #     pending.task_uid,
                # )
                return False

            try:
                task = self._task_registry.allocate(
                    robot.robot_id,
                    pending.task_uid,
                )
            except (TaskRegistryFull, ValueError) as exc:
                LOGGER.warning(
                    "Chưa thể cấp robot cho task %s: %s",
                    pending.task_uid,
                    exc,
                )
                return False

            pending = replace(
                pending,
                robot_id=task.robot_id,
                task_id=task.task_id,
            )
            with self._lock:
                self._pending_assignments[pending.task_uid] = pending

        elif (
            pending.robot_id != task.robot_id
            or pending.task_id != task.task_id
        ):
            # Registry là nguồn sự thật cho reservation. Gắn task hiện có vào
            # pending và gửi lại cùng task_id thay vì coi reservation là ACK.
            pending = replace(
                pending,
                robot_id=task.robot_id,
                task_id=task.task_id,
            )
            with self._lock:
                self._pending_assignments[pending.task_uid] = pending

        self._task_activity_store.mark_assigning(
            pending.task_uid,
            task.robot_id,
            task.task_id,
        )

        message = TaskAssign(
            robot_id=task.robot_id,
            task_id=task.task_id,
            x=pending.x,
            y=pending.y,
            theta=pending.theta,
        )

        ack = self._uart.send_with_retry_ack(
            message,
            reference_id=task.task_id,
            timeout=self._ack_timeout_seconds,
            max_retries=self._max_retries,
        )
        if ack is None or ack.result_code != AckResultCode.ACCEPTED:
            self._task_activity_store.increment_retry(pending.task_uid)
            if ack is None:
                LOGGER.warning(
                    "Chưa nhận ACK cho TaskAssign; giữ nguyên task để thử lại: "
                    "task_uid=%s, robot_id=%s, task_id=%s",
                    pending.task_uid,
                    task.robot_id,
                    task.task_id,
                )
            else:
                LOGGER.warning(
                    "Robot từ chối TaskAssign; giữ nguyên task để thử lại: "
                    "task_uid=%s, robot_id=%s, task_id=%s, reason=%s(%s)",
                    pending.task_uid,
                    task.robot_id,
                    task.task_id,
                    _ack_reason_name(ack.reason_code),
                    ack.reason_code,
                )
            return False

        self._remove_pending_assignment(pending.task_uid)
        self._task_activity_store.mark_assigned(pending.task_uid)
        return True

    # ─────────────────────────────────────────────────────────────────────────
    def _try_cancel(self, task_uid: str) -> bool:
        """Thử hoàn tất yêu cầu hủy của một task runtime theo UID."""
        task_activity = self._task_activity_store.get(task_uid)
        if task_activity is None:
            self._remove_pending_cancellation(task_uid)
            return True

        task = self._task_registry.get_by_uid(task_uid)
        if task is None:
            self._task_activity_store.mark_canceled(task_uid)
            if (
                task_activity.origin == "zone"
                and task_activity.zone_id is not None
            ):
                self._decision_engine.on_service_cancelled(task_activity.zone_id)
            self._remove_pending_cancellation(task_uid)
            return True

        message = TaskCancel(robot_id=task.robot_id, task_id=task.task_id)
        ack = self._uart.send_with_retry_ack(
            message,
            reference_id=task.task_id,
            timeout=self._ack_timeout_seconds,
            max_retries=self._max_retries,
        )
        if ack is None or ack.result_code != AckResultCode.ACCEPTED:
            self._task_activity_store.increment_retry(task_uid)
            if ack is None:
                LOGGER.warning(
                    "Chưa nhận ACK cho TaskCancel; giữ decision để thử lại: "
                    "task_uid=%s, robot_id=%s, task_id=%s",
                    task_uid,
                    task.robot_id,
                    task.task_id,
                )
            else:
                LOGGER.warning(
                    "Robot từ chối TaskCancel; giữ decision để thử lại: "
                    "task_uid=%s, robot_id=%s, task_id=%s, reason=%s(%s)",
                    task_uid,
                    task.robot_id,
                    task.task_id,
                    _ack_reason_name(ack.reason_code),
                    ack.reason_code,
                )
            return False

        self._task_activity_store.mark_canceled(task_uid)
        self._task_registry.release(task.robot_id, task.task_id)
        if task_activity.origin == "zone" and task_activity.zone_id is not None:
            self._decision_engine.on_service_cancelled(task_activity.zone_id)
        self._remove_pending_cancellation(task_uid)
        return True

    # ─────────────────────────────────────────────────────────────────────────
    def _send_task_status_ack(self, message: TaskStatus) -> None:
        """Gửi ACK một lần cho TaskStatus; robot chịu trách nhiệm retry status."""
        ack = Ack(
            robot_id=message.robot_id,
            acked_type=MessageType.TASK_STATUS,
            reference_id=message.task_id,
            result_code=AckResultCode.ACCEPTED,
            reason_code=AckReasonCode.NONE,
        )
        if not self._uart.send_message(ack):
            LOGGER.warning(
                "Không gửi được ACK cho TaskStatus: robot_id=%s, task_id=%s",
                message.robot_id,
                message.task_id,
            )

    # ─────────────────────────────────────────────────────────────────────────
    def _remove_pending_assignment(self, task_uid: str) -> None:
        """Xóa assignment khỏi hàng đợi theo UID runtime."""
        with self._lock:
            self._pending_assignments.pop(task_uid, None)

    # ─────────────────────────────────────────────────────────────────────────
    def _remove_pending_cancellation(self, task_uid: str) -> None:
        """Xóa yêu cầu cancel khỏi hàng đợi theo UID runtime."""
        with self._lock:
            self._pending_cancellations.discard(task_uid)


# ─────────────────────────────────────────────────────────────────────────────
def _build_pending_assignment(
    decision: DispatchDecision,
) -> Optional[_PendingAssignment]:
    """Chụp goal pose của decision để dùng an toàn khi phải retry về sau."""
    try:
        return _PendingAssignment(
            task_uid="",
            x=float(decision.zone.goal_pose["x"]),
            y=float(decision.zone.goal_pose["y"]),
            theta=float(decision.zone.goal_pose["theta"]),
            priority=TaskPriority(decision.priority.value),
        )
    except (KeyError, TypeError, ValueError) as exc:
        LOGGER.error(
            "Goal pose không hợp lệ cho zone '%s' (id=%s): %s",
            decision.zone.name,
            decision.zone_id,
            exc,
        )
        return None


# ─────────────────────────────────────────────────────────────────────────────
def _parse_goal_pose(goal_pose: dict[str, float]) -> tuple[float, float, float]:
    """Đọc và kiểm tra goal pose của task thủ công."""
    try:
        parsed = (
            float(goal_pose["x"]),
            float(goal_pose["y"]),
            float(goal_pose["theta"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Goal pose của task thủ công không hợp lệ") from exc
    if not all(math.isfinite(value) for value in parsed):
        raise ValueError("Goal pose của task thủ công phải là số hữu hạn")
    return parsed


# ─────────────────────────────────────────────────────────────────────────────
def _decision_dispatch_sort_key(
    decision: DispatchDecision,
) -> tuple[int, int]:
    """Xếp cancel trước assign, rồi xếp assign theo priority giảm dần."""
    if decision.action is DispatchAction.TASK_CANCEL:
        return 0, 0
    if decision.action is DispatchAction.TASK_ASSIGN:
        return 1, -TASK_PRIORITY_RANK[TaskPriority(decision.priority.value)]
    return 2, 0


# ─────────────────────────────────────────────────────────────────────────────
def _pending_assignment_sort_key(
    pending: _PendingAssignment,
) -> tuple[int, int]:
    """Xếp task chờ theo priority giảm dần và FIFO trong cùng một mức."""
    return -TASK_PRIORITY_RANK[pending.priority], pending.enqueue_sequence
