"""Thực thi các quyết định dispatch bằng giao thức robot nhị phân V2."""

from __future__ import annotations

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
from src.zones_management import Zone
from utils import LOGGER


DEFAULT_ACK_TIMEOUT_SECONDS = 1.0
DEFAULT_MAX_RETRIES = 5


# ─────────────────────────────────────────────────────────────────────────────
class UartTransport(Protocol):
    """Phần API UART mà RobotDispatcherV2 cần sử dụng."""

    def set_handler(self, message_type: int, handler) -> None:
        """Đăng ký handler cho một loại message."""

    def add_handler(self, message_type: int, handler) -> None:
        """Thêm handler mà không ghi đè handler hiện có."""

    def send_message(self, message: MessageBase) -> bool:
        """Gửi một message đúng một lần."""

    def send_with_retry(
        self,
        message: MessageBase,
        task_id: int,
        timeout: float = 1.0,
        max_retries: int = 5,
    ) -> bool:
        """Gửi message và thử lại cho tới khi nhận ACK hoặc hết số lần thử."""


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class _PendingAssignment:
    """Snapshot bất biến của một yêu cầu assign đang chờ thực thi."""

    zone_id: str
    x: float
    y: float
    theta: float
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
        ack_timeout_seconds: float = DEFAULT_ACK_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        register_handlers: bool = True,
        register_heartbeat_handler: bool = True,
    ) -> None:
        """Khởi tạo dispatcher và tùy chọn đăng ký các UART handler cần thiết."""
        self._uart = uart
        self._decision_engine = decision_engine or DispatchDecisionEngine()
        self._robot_state_store = robot_state_store or RobotStateStore()
        self._task_registry = task_registry or TaskRegistry()
        self._ack_timeout_seconds = ack_timeout_seconds
        self._max_retries = max_retries
        self._register_heartbeat_handler = register_heartbeat_handler

        self._pending_assignments: dict[str, _PendingAssignment] = {}
        self._pending_cancellations: set[str] = set()
        self._lock = threading.RLock()
        self._handlers_registered = False
        self._registered_with_add_handler = False

        if register_handlers:
            self.register_uart_handlers()

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
        """Thực thi một danh sách decision và trả kết quả tức thời tương ứng."""
        return [self.process_decision(decision) for decision in decisions]

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

            with self._lock:
                waiting_for_cancel = (
                    decision.zone_id in self._pending_cancellations
                )
                self._pending_assignments[decision.zone_id] = pending

            # Task cũ của zone phải hủy xong trước khi assign task mới.
            if waiting_for_cancel:
                return False

            return self._try_assign(pending)

        if decision.action is DispatchAction.TASK_CANCEL:
            with self._lock:
                # Dừng việc retry TaskAssign khi đã phát sinh TaskCancel.
                self._pending_assignments.pop(decision.zone_id, None)
                self._pending_cancellations.add(decision.zone_id)

            return self._try_cancel(decision.zone_id)

        LOGGER.warning("Bỏ qua dispatch action không được hỗ trợ: %s", decision.action)
        return False

    # ─────────────────────────────────────────────────────────────────────────
    def tick(self) -> int:
        """
        Thử lại các decision chưa thực thi được.

        Cancel luôn được thử trước assign để tránh giao task mới trong khi task
        cũ của một zone vẫn chưa hủy xong. Trả số decision hoàn tất trong tick.
        """
        with self._lock:
            cancellation_zone_ids = list(self._pending_cancellations)
            assignments = list(self._pending_assignments.values())

        completed_count = 0

        for zone_id in cancellation_zone_ids:
            if self._try_cancel(zone_id):
                completed_count += 1

        for pending in assignments:
            with self._lock:
                if pending.zone_id in self._pending_cancellations:
                    continue
                if self._pending_assignments.get(pending.zone_id) != pending:
                    continue

            if self._try_assign(pending):
                completed_count += 1

        return completed_count

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
        self._remove_pending_assignment(task.zone_id)

        if status is TaskStatusCode.COMPLETED:
            released = self._task_registry.release(message.robot_id, message.task_id)
            if released is not None:
                self._decision_engine.on_service_completed(released.zone_id)

        elif status is TaskStatusCode.FAILED:
            # Không tự giao lại task vì retry nghiệp vụ cần policy riêng.
            released = self._task_registry.release(message.robot_id, message.task_id)
            if released is not None:
                self._decision_engine.on_service_failed(released.zone_id)
            LOGGER.warning(
                "Task thất bại: robot_id=%s, task_id=%s, zone_id=%s",
                message.robot_id,
                message.task_id,
                task.zone_id,
            )

        self._send_task_status_ack(message)

    # ─────────────────────────────────────────────────────────────────────────
    def get_assigned_task(self, zone_id: str) -> Optional[AssignedTask]:
        """Lấy task hiện đang được giữ chỗ cho một zone."""
        return self._task_registry.get_by_zone(zone_id)

    # ─────────────────────────────────────────────────────────────────────────
    def pending_count(self) -> int:
        """Trả tổng số assign/cancel đang chờ thử lại."""
        with self._lock:
            return len(self._pending_assignments) + len(self._pending_cancellations)

    # ─────────────────────────────────────────────────────────────────────────
    def _try_assign(self, pending: _PendingAssignment) -> bool:
        """Thử chọn robot, cấp task và gửi TaskAssign cho một yêu cầu đang chờ."""
        task = self._task_registry.get_by_zone(pending.zone_id)

        if task is None:
            # Registry từng có task nhưng nay không còn nghĩa là terminal status
            # đã xử lý task trong lúc một lần gửi đang chờ ACK.
            if pending.robot_id is not None and pending.task_id is not None:
                self._remove_pending_assignment(pending.zone_id)
                return True

            robot = self._robot_state_store.nearest_idle_robot(
                pending.x,
                pending.y,
                excluded_robot_ids=self._task_registry.reserved_robot_ids(),
            )
            if robot is None:
                LOGGER.info(
                    "Chưa có robot IDLE cho zone %s; giữ lại để thử sau.",
                    pending.zone_id,
                )
                return False

            try:
                task = self._task_registry.allocate(robot.robot_id, pending.zone_id)
            except (TaskRegistryFull, ValueError) as exc:
                LOGGER.warning("Chưa thể cấp task cho zone %s: %s", pending.zone_id, exc)
                return False

            pending = replace(
                pending,
                robot_id=task.robot_id,
                task_id=task.task_id,
            )
            with self._lock:
                self._pending_assignments[pending.zone_id] = pending

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
                self._pending_assignments[pending.zone_id] = pending

        message = TaskAssign(
            robot_id=task.robot_id,
            task_id=task.task_id,
            x=pending.x,
            y=pending.y,
            theta=pending.theta,
        )

        sent = self._uart.send_with_retry(
            message,
            task_id=task.task_id,
            timeout=self._ack_timeout_seconds,
            max_retries=self._max_retries,
        )
        if not sent:
            LOGGER.warning(
                "Chưa nhận ACK cho TaskAssign; giữ nguyên task để thử lại: "
                "zone_id=%s, robot_id=%s, task_id=%s",
                pending.zone_id,
                task.robot_id,
                task.task_id,
            )
            return False

        self._remove_pending_assignment(pending.zone_id)
        return True

    # ─────────────────────────────────────────────────────────────────────────
    def _try_cancel(self, zone_id: str) -> bool:
        """Thử gửi TaskCancel cho task hiện tại của zone."""
        task = self._task_registry.get_by_zone(zone_id)
        if task is None:
            self._decision_engine.on_service_cancelled(zone_id)
            self._remove_pending_cancellation(zone_id)
            return True

        message = TaskCancel(robot_id=task.robot_id, task_id=task.task_id)
        sent = self._uart.send_with_retry(
            message,
            task_id=task.task_id,
            timeout=self._ack_timeout_seconds,
            max_retries=self._max_retries,
        )
        if not sent:
            LOGGER.warning(
                "Gửi TaskCancel chưa thành công; giữ decision để thử lại: "
                "zone_id=%s, robot_id=%s, task_id=%s",
                zone_id,
                task.robot_id,
                task.task_id,
            )
            return False

        self._task_registry.release(task.robot_id, task.task_id)
        self._decision_engine.on_service_cancelled(zone_id)
        self._remove_pending_cancellation(zone_id)
        return True

    # ─────────────────────────────────────────────────────────────────────────
    def _send_task_status_ack(self, message: TaskStatus) -> None:
        """Gửi ACK một lần cho TaskStatus; robot chịu trách nhiệm retry status."""
        ack = Ack(
            robot_id=message.robot_id,
            acked_type=MessageType.TASK_STATUS,
            task_id=message.task_id,
        )
        if not self._uart.send_message(ack):
            LOGGER.warning(
                "Không gửi được ACK cho TaskStatus: robot_id=%s, task_id=%s",
                message.robot_id,
                message.task_id,
            )

    # ─────────────────────────────────────────────────────────────────────────
    def _remove_pending_assignment(self, zone_id: str) -> None:
        with self._lock:
            self._pending_assignments.pop(zone_id, None)

    # ─────────────────────────────────────────────────────────────────────────
    def _remove_pending_cancellation(self, zone_id: str) -> None:
        with self._lock:
            self._pending_cancellations.discard(zone_id)


# ─────────────────────────────────────────────────────────────────────────────
def _build_pending_assignment(
    decision: DispatchDecision,
) -> Optional[_PendingAssignment]:
    """Chụp goal pose của decision để dùng an toàn khi phải retry về sau."""
    try:
        return _PendingAssignment(
            zone_id=decision.zone_id,
            x=float(decision.zone.goal_pose["x"]),
            y=float(decision.zone.goal_pose["y"]),
            theta=float(decision.zone.goal_pose["theta"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        LOGGER.error("Goal pose không hợp lệ cho zone %s: %s", decision.zone_id, exc)
        return None
