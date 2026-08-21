from __future__ import annotations

import time
import threading

import numpy as np

from src.detection import Detection
from src.dispatch_decision import (
    DispatchAction,
    DispatchDecision,
    DispatchDecisionEngine,
    PersonServiceState,
    ReIdDecisionPolicy,
    ZoneServiceState,
)
from src.robot_dispatch_v2 import (
    RobotDispatcherV2,
    TaskActivityStore,
    TaskPriority,
    TaskRegistry,
)
from src.robot_dispatch_v2.datatypes import (
    Ack,
    AckReasonCode,
    AckResultCode,
    Heartbeat,
    MessageType,
    RobotStateCode,
    TaskAssign,
    TaskCancel,
    TaskFailureReasonCode,
    TaskStatus,
    TaskStatusCode,
)
from src.zones_management import Zone, ZonePriority, ZoneState


# ─────────────────────────────────────────────────────────────────────────────
class FakeUart:
    """UART giả có handler, subscriber và kết quả gửi cấu hình được."""

    def __init__(self) -> None:
        self.handlers = {}
        self.additional_handlers = {}
        self.sent = []
        self.outcomes = {}

    def set_outcomes(self, message_class, *outcomes: bool) -> None:
        self.outcomes[message_class] = list(outcomes)

    def set_handler(self, message_type, handler) -> None:
        self.handlers[int(message_type)] = handler

    def add_handler(self, message_type, handler) -> None:
        handlers = self.additional_handlers.setdefault(int(message_type), [])
        if handler not in handlers:
            handlers.append(handler)

    def remove_handler(self, message_type, handler) -> None:
        handlers = self.additional_handlers.get(int(message_type), [])
        if handler in handlers:
            handlers.remove(handler)

    def send_message(self, message) -> bool:
        self.sent.append(message)
        return True

    def send_with_retry_ack(
        self,
        message,
        reference_id: int,
        timeout: float = 1.0,
        max_retries: int = 5,
    ):
        """Giả lập retry và trả ACK đầy đủ cho dispatcher."""
        self.sent.append(message)
        outcomes = self.outcomes.get(type(message), [])
        accepted = outcomes.pop(0) if outcomes else True
        if isinstance(accepted, Ack):
            return accepted
        if not accepted:
            return None
        return Ack(
            robot_id=message.robot_id,
            acked_type=message.MESSAGE_TYPE,
            reference_id=reference_id,
            result_code=AckResultCode.ACCEPTED,
            reason_code=AckReasonCode.NONE,
        )

    def emit(self, message) -> None:
        handler = self.handlers.get(int(message.MESSAGE_TYPE))
        if handler is not None:
            handler(message)
        for subscriber in self.additional_handlers.get(
            int(message.MESSAGE_TYPE),
            (),
        ):
            subscriber(message)


class BlockingAckUart(FakeUart):
    """UART giả giữ ACK để kiểm tra worker nền không làm chặn caller."""

    def __init__(self) -> None:
        """Khởi tạo các event điều khiển thời điểm trả ACK."""
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    # ─────────────────────────────────────────────────────────────────────────
    def send_with_retry_ack(
        self,
        message,
        reference_id: int,
        timeout: float = 1.0,
        max_retries: int = 5,
    ):
        """Giữ worker tại điểm chờ ACK rồi trả ACK chấp nhận khi được mở khóa."""
        del timeout, max_retries
        self.sent.append(message)
        self.started.set()
        self.release.wait(timeout=2.0)
        return Ack(
            robot_id=message.robot_id,
            acked_type=message.MESSAGE_TYPE,
            reference_id=reference_id,
            result_code=AckResultCode.ACCEPTED,
            reason_code=AckReasonCode.NONE,
        )


# ─────────────────────────────────────────────────────────────────────────────
def _zone(
    zone_id: str,
    *,
    state: ZoneState = ZoneState.OCCUPIED,
    goal_pose=None,
    priority: ZonePriority = ZonePriority.LOW,
    service_point: tuple[float, float] | None = None,
) -> Zone:
    return Zone(
        camera_id="camera-1",
        camera_name="Camera 1",
        id=zone_id,
        name=zone_id,
        pts=np.empty((0, 2), dtype=np.int32),
        goal_pose=goal_pose or {"x": 1.0, "y": 2.0, "theta": 0.0},
        priority=priority,
        service_point=service_point,
        state=state,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _decision(action: DispatchAction, zone: Zone) -> DispatchDecision:
    return DispatchDecision(
        action=action,
        zone_id=str(zone.id or zone.key),
        zone=zone,
        previous_state=ZoneState.PENDING_ENTER,
        current_state=zone.state,
        priority=zone.priority,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _heartbeat(
    robot_id: int = 1,
    *,
    state: RobotStateCode = RobotStateCode.IDLE,
    timestamp: int | None = None,
) -> Heartbeat:
    return Heartbeat(
        robot_id=robot_id,
        timestamp=timestamp or int(time.time()),
        x=0.0,
        y=0.0,
        theta=0.0,
        state_code=state,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _assigned_task_for_zone(
    dispatcher: RobotDispatcherV2,
    zone_id: str,
):
    """Tra reservation của task zone qua secondary index zone sang UID."""
    task_uid = dispatcher.task_activity_store.get_active_uid_by_zone(zone_id)
    if task_uid is None:
        return None
    return dispatcher.get_assigned_task_by_uid(task_uid)


# ─────────────────────────────────────────────────────────────────────────────
def test_task_registry_indexes_reservations_only_by_uid() -> None:
    """Registry không cần zone ID để cấp, tra và giải phóng reservation."""
    registry = TaskRegistry()

    first = registry.allocate(robot_id=1, task_uid="task-a")
    second = registry.allocate(robot_id=2, task_uid="task-b")

    assert registry.get_by_uid("task-a") == first
    assert registry.get_by_uid("task-b") == second
    assert registry.allocate(robot_id=3, task_uid="task-a") == first
    assert registry.release(first.robot_id, first.task_id) == first
    assert registry.get_by_uid("task-a") is None


# ─────────────────────────────────────────────────────────────────────────────
def test_lost_assign_ack_retries_same_robot_and_task() -> None:
    uart = FakeUart()
    uart.set_outcomes(TaskAssign, False, True)
    dispatcher = RobotDispatcherV2(uart, retry_backoff_seconds=0)
    dispatcher.on_heartbeat(_heartbeat())
    zone = _zone("zone-1")

    assert not dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, zone)
    )
    reserved = _assigned_task_for_zone(dispatcher, zone.id)
    assert reserved is not None
    assert dispatcher.pending_count() == 1

    assert dispatcher.tick() == 1
    assignments = [message for message in uart.sent if isinstance(message, TaskAssign)]
    assert len(assignments) == 2
    assert {
        (message.robot_id, message.task_id)
        for message in assignments
    } == {(reserved.robot_id, reserved.task_id)}


# ─────────────────────────────────────────────────────────────────────────────
def test_robot_busy_requeues_task_to_another_robot() -> None:
    """ACK ROBOT_BUSY giải phóng reservation và chọn robot khác sau cooldown."""
    uart = FakeUart()
    uart.set_outcomes(
        TaskAssign,
        Ack(
            robot_id=1,
            acked_type=MessageType.TASK_ASSIGN,
            reference_id=0,
            result_code=AckResultCode.REJECTED,
            reason_code=AckReasonCode.ROBOT_BUSY,
        ),
        True,
    )
    activity_store = TaskActivityStore()
    dispatcher = RobotDispatcherV2(
        uart,
        task_activity_store=activity_store,
        retry_backoff_seconds=0,
        robot_rejection_cooldown_seconds=10,
    )
    dispatcher.on_heartbeat(_heartbeat(robot_id=1))
    dispatcher.on_heartbeat(_heartbeat(robot_id=2))
    zone = _zone("zone-busy")

    assert not dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, zone)
    )
    waiting = activity_store.snapshot()["tasks"][0]
    assert waiting["status"] == "WAITING_ROBOT"
    assert waiting["last_ack_reason"] == "ROBOT_BUSY"
    assert waiting["robot_id"] is None

    assert dispatcher.tick() == 1
    assigned = _assigned_task_for_zone(dispatcher, zone.id)
    assert assigned is not None
    assert assigned.robot_id == 2


# ─────────────────────────────────────────────────────────────────────────────
def test_invalid_command_fails_assignment_without_retry() -> None:
    """ACK INVALID_COMMAND kết thúc task ngay thay vì lặp vô hạn."""
    uart = FakeUart()
    uart.set_outcomes(
        TaskAssign,
        Ack(
            robot_id=1,
            acked_type=MessageType.TASK_ASSIGN,
            reference_id=0,
            result_code=AckResultCode.REJECTED,
            reason_code=AckReasonCode.INVALID_COMMAND,
        ),
    )
    activity_store = TaskActivityStore()
    engine = DispatchDecisionEngine()
    dispatcher = RobotDispatcherV2(
        uart,
        decision_engine=engine,
        task_activity_store=activity_store,
    )
    dispatcher.on_heartbeat(_heartbeat())
    zone = _zone("zone-invalid", state=ZoneState.PENDING_ENTER)

    assert dispatcher.process_zones([zone]) == []
    zone.state = ZoneState.OCCUPIED
    dispatcher.process_zones([zone])
    failed = activity_store.snapshot()["tasks"][0]
    assert failed["status"] == "FAILED"
    assert failed["last_ack_reason"] == "INVALID_COMMAND"
    assert failed["failure_reason"] == "ASSIGN_REJECTED_INVALID_COMMAND"
    assert dispatcher.pending_count() == 0
    assert engine.get_service_state(zone.id) is ZoneServiceState.FAILED


# ─────────────────────────────────────────────────────────────────────────────
def test_assign_timeout_stops_at_global_attempt_limit() -> None:
    """Mất ACK chỉ retry tới giới hạn dispatch toàn cục rồi kết thúc task."""
    uart = FakeUart()
    uart.set_outcomes(TaskAssign, False, False, True)
    activity_store = TaskActivityStore()
    dispatcher = RobotDispatcherV2(
        uart,
        task_activity_store=activity_store,
        max_dispatch_attempts=2,
        retry_backoff_seconds=0,
    )
    dispatcher.on_heartbeat(_heartbeat())
    zone = _zone("zone-timeout")

    assert not dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, zone)
    )
    assert dispatcher.tick() == 1

    failed = activity_store.snapshot()["tasks"][0]
    assert failed["status"] == "FAILED"
    assert failed["retry_count"] == 2
    assert failed["failure_reason"] == "ASSIGN_ACK_TIMEOUT_RETRY_EXHAUSTED"
    assert failed["failure_reason_code"] == TaskFailureReasonCode.DISPATCH_TIMEOUT
    assert dispatcher.pending_count() == 0
    assert dispatcher.get_assigned_task_by_uid(failed["uid"]) is not None


# ─────────────────────────────────────────────────────────────────────────────
def test_zone_rejects_new_assign_until_pending_cancel_finishes() -> None:
    """Không tạo task zone thứ hai trước khi task cũ hủy xong."""
    uart = FakeUart()
    uart.set_outcomes(TaskCancel, False, True)
    dispatcher = RobotDispatcherV2(uart, retry_backoff_seconds=0)
    dispatcher.on_heartbeat(_heartbeat())
    zone = _zone("zone-1")

    assert dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, zone)
    )
    old_task = _assigned_task_for_zone(dispatcher, zone.id)
    assert old_task is not None

    assert not dispatcher.process_decision(
        _decision(DispatchAction.TASK_CANCEL, zone)
    )
    assert not dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, zone)
    )
    assert dispatcher.pending_count() == 1

    assert dispatcher.tick() == 1
    assert dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, zone)
    )
    new_task = _assigned_task_for_zone(dispatcher, zone.id)
    assert new_task is not None
    assert new_task.task_id != old_task.task_id
    assert [type(message) for message in uart.sent] == [
        TaskAssign,
        TaskCancel,
        TaskCancel,
        TaskAssign,
    ]


# ─────────────────────────────────────────────────────────────────────────────
def test_no_idle_robot_keeps_assignment_until_tick() -> None:
    uart = FakeUart()
    dispatcher = RobotDispatcherV2(uart)
    zone = _zone("zone-1")

    assert not dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, zone)
    )
    assert dispatcher.pending_count() == 1

    dispatcher.on_heartbeat(_heartbeat())
    assert dispatcher.tick() == 1
    assert _assigned_task_for_zone(dispatcher, zone.id) is not None


# ─────────────────────────────────────────────────────────────────────────────
def test_pending_assignments_use_priority_then_fifo() -> None:
    """Kiểm tra hàng đợi chọn priority cao trước và giữ FIFO khi cùng mức."""
    uart = FakeUart()
    dispatcher = RobotDispatcherV2(uart)
    low_first = _zone(
        "low-first",
        priority=ZonePriority.LOW,
        goal_pose={"x": 1.0, "y": 0.0, "theta": 0.0},
    )
    low_second = _zone(
        "low-second",
        priority=ZonePriority.LOW,
        goal_pose={"x": 2.0, "y": 0.0, "theta": 0.0},
    )
    medium = _zone(
        "medium",
        priority=ZonePriority.MEDIUM,
        goal_pose={"x": 3.0, "y": 0.0, "theta": 0.0},
    )
    high = _zone(
        "high",
        priority=ZonePriority.HIGH,
        goal_pose={"x": 4.0, "y": 0.0, "theta": 0.0},
    )

    for zone in (low_first, low_second, medium, high):
        assert not dispatcher.process_decision(
            _decision(DispatchAction.TASK_ASSIGN, zone),
        )

    dispatcher.on_heartbeat(_heartbeat())
    assert dispatcher.tick() == 1
    assert _assigned_task_for_zone(dispatcher, high.id) is not None

    high_task = _assigned_task_for_zone(dispatcher, high.id)
    assert high_task is not None
    dispatcher.on_task_status(
        TaskStatus(high_task.robot_id, high_task.task_id, TaskStatusCode.COMPLETED),
    )
    assert dispatcher.tick() == 1
    assert _assigned_task_for_zone(dispatcher, medium.id) is not None

    medium_task = _assigned_task_for_zone(dispatcher, medium.id)
    assert medium_task is not None
    dispatcher.on_task_status(
        TaskStatus(
            medium_task.robot_id,
            medium_task.task_id,
            TaskStatusCode.COMPLETED,
        ),
    )
    assert dispatcher.tick() == 1
    assert _assigned_task_for_zone(dispatcher, low_first.id) is not None


# ─────────────────────────────────────────────────────────────────────────────
def test_manual_task_uses_shared_priority_queue() -> None:
    """Task manual được xếp chung với task zone và có thể đổi priority khi chờ."""
    uart = FakeUart()
    activity_store = TaskActivityStore()
    dispatcher = RobotDispatcherV2(uart, task_activity_store=activity_store)
    zone = _zone("zone-medium", priority=ZonePriority.MEDIUM)

    manual_uid = dispatcher.enqueue_manual_task(
        camera_id="camera-1",
        camera_name="Camera 1",
        target_pixel=(960.0, 540.0),
        goal_pose={"x": 9.0, "y": 8.0, "theta": 0.5},
        priority=TaskPriority.LOW,
    )
    assert not dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, zone)
    )
    assert dispatcher.change_task_priority(manual_uid, TaskPriority.HIGH)

    manual_activity = activity_store.get(manual_uid)
    assert manual_activity is not None
    assert manual_activity.origin == "manual"
    assert manual_activity.zone_id is None
    assert manual_activity.priority == "high"

    dispatcher.on_heartbeat(_heartbeat())
    assert dispatcher.tick() == 1
    assigned = dispatcher.get_assigned_task_by_uid(manual_uid)
    assert assigned is not None
    assert isinstance(uart.sent[-1], TaskAssign)
    assert (uart.sent[-1].x, uart.sent[-1].y) == (9.0, 8.0)


# ─────────────────────────────────────────────────────────────────────────────
def test_cancel_waiting_manual_task_does_not_send_uart() -> None:
    """Task manual chưa có robot được hủy ngay mà không phát TaskCancel."""
    uart = FakeUart()
    activity_store = TaskActivityStore()
    dispatcher = RobotDispatcherV2(uart, task_activity_store=activity_store)
    task_uid = dispatcher.enqueue_manual_task(
        camera_id="camera-1",
        camera_name="Camera 1",
        target_pixel=(100.0, 200.0),
        goal_pose={"x": 1.0, "y": 2.0, "theta": 0.0},
        priority=TaskPriority.LOW,
    )

    assert dispatcher.cancel_task(task_uid)
    assert dispatcher.pending_count() == 0
    assert activity_store.get(task_uid).status == "CANCELED"
    assert not any(isinstance(message, TaskCancel) for message in uart.sent)
    assert dispatcher.cancel_task(task_uid)


# ─────────────────────────────────────────────────────────────────────────────
def test_cancel_assigned_manual_task_sends_uart() -> None:
    """Task manual đã assign dùng cùng đường TaskCancel với task zone."""
    uart = FakeUart()
    activity_store = TaskActivityStore()
    dispatcher = RobotDispatcherV2(uart, task_activity_store=activity_store)
    dispatcher.on_heartbeat(_heartbeat())
    task_uid = dispatcher.enqueue_manual_task(
        camera_id="camera-1",
        camera_name="Camera 1",
        target_pixel=(100.0, 200.0),
        goal_pose={"x": 1.0, "y": 2.0, "theta": 0.0},
        priority=TaskPriority.HIGH,
    )

    assert dispatcher.get_assigned_task_by_uid(task_uid) is not None
    assert dispatcher.cancel_task(task_uid)
    assert activity_store.get(task_uid).status == "CANCELED"
    assert isinstance(uart.sent[-1], TaskCancel)
    assert dispatcher.get_assigned_task_by_uid(task_uid) is None


# ─────────────────────────────────────────────────────────────────────────────
def test_rejected_cancel_fails_task_but_keeps_robot_reserved() -> None:
    """Cancel bị từ chối kết thúc control flow nhưng không giao chồng task."""
    uart = FakeUart()
    activity_store = TaskActivityStore()
    dispatcher = RobotDispatcherV2(uart, task_activity_store=activity_store)
    dispatcher.on_heartbeat(_heartbeat())
    task_uid = dispatcher.enqueue_manual_task(
        camera_id="camera-1",
        camera_name="Camera 1",
        target_pixel=(100.0, 200.0),
        goal_pose={"x": 1.0, "y": 2.0, "theta": 0.0},
        priority=TaskPriority.HIGH,
    )
    assigned = dispatcher.get_assigned_task_by_uid(task_uid)
    assert assigned is not None
    uart.set_outcomes(
        TaskCancel,
        Ack(
            robot_id=assigned.robot_id,
            acked_type=MessageType.TASK_CANCEL,
            reference_id=assigned.task_id,
            result_code=AckResultCode.REJECTED,
            reason_code=AckReasonCode.INVALID_COMMAND,
        ),
    )

    assert dispatcher.cancel_task(task_uid)

    failed = activity_store.get(task_uid)
    assert failed is not None
    assert failed.status == "FAILED"
    assert failed.failure_reason == "CANCEL_REJECTED_INVALID_COMMAND"
    assert dispatcher.get_assigned_task_by_uid(task_uid) == assigned
    assert dispatcher.pending_count() == 0


# ─────────────────────────────────────────────────────────────────────────────
def test_cancel_timeout_stops_at_global_attempt_limit() -> None:
    """Cancel mất ACK dừng retry nhưng giữ reservation vì trạng thái mơ hồ."""
    uart = FakeUart()
    activity_store = TaskActivityStore()
    dispatcher = RobotDispatcherV2(
        uart,
        task_activity_store=activity_store,
        max_dispatch_attempts=2,
        retry_backoff_seconds=0,
    )
    dispatcher.on_heartbeat(_heartbeat())
    task_uid = dispatcher.enqueue_manual_task(
        camera_id="camera-1",
        camera_name="Camera 1",
        target_pixel=(100.0, 200.0),
        goal_pose={"x": 1.0, "y": 2.0, "theta": 0.0},
        priority=TaskPriority.HIGH,
    )
    assigned = dispatcher.get_assigned_task_by_uid(task_uid)
    assert assigned is not None
    uart.set_outcomes(TaskCancel, False, False, True)

    assert not dispatcher.cancel_task(task_uid)
    assert dispatcher.tick() == 1

    failed = activity_store.get(task_uid)
    assert failed is not None
    assert failed.status == "FAILED"
    assert failed.failure_reason == "CANCEL_ACK_TIMEOUT_RETRY_EXHAUSTED"
    assert dispatcher.get_assigned_task_by_uid(task_uid) == assigned
    assert dispatcher.pending_count() == 0


# ─────────────────────────────────────────────────────────────────────────────
def test_web_cancel_zone_task_updates_decision_engine() -> None:
    """Cancel chủ động task zone đồng bộ trạng thái service của decision engine."""
    uart = FakeUart()
    engine = DispatchDecisionEngine()
    activity_store = TaskActivityStore()
    dispatcher = RobotDispatcherV2(
        uart,
        decision_engine=engine,
        task_activity_store=activity_store,
    )
    dispatcher.on_heartbeat(_heartbeat())
    zone = _zone("zone-1", state=ZoneState.PENDING_ENTER)
    dispatcher.process_zones([zone])
    zone.state = ZoneState.OCCUPIED
    dispatcher.process_zones([zone])
    task_uid = activity_store.get_active_uid_by_zone(zone.id)
    assert task_uid is not None

    assert dispatcher.cancel_task(task_uid)
    assert activity_store.get(task_uid).status == "CANCELED"
    assert engine.get_service_state(zone.id) is ZoneServiceState.NOT_REQUESTED


# ─────────────────────────────────────────────────────────────────────────────
def test_batch_decisions_assign_high_priority_first() -> None:
    """Kiểm tra decision cùng batch được gửi theo priority thay vì thứ tự input."""
    uart = FakeUart()
    dispatcher = RobotDispatcherV2(uart)
    dispatcher.on_heartbeat(_heartbeat(robot_id=1))
    dispatcher.on_heartbeat(_heartbeat(robot_id=2))
    low = _zone(
        "low",
        priority=ZonePriority.LOW,
        goal_pose={"x": 1.0, "y": 0.0, "theta": 0.0},
    )
    high = _zone(
        "high",
        priority=ZonePriority.HIGH,
        goal_pose={"x": 9.0, "y": 0.0, "theta": 0.0},
    )

    assert dispatcher.process_decisions([
        _decision(DispatchAction.TASK_ASSIGN, low),
        _decision(DispatchAction.TASK_ASSIGN, high),
    ]) == [True, True]

    assignments = [message for message in uart.sent if isinstance(message, TaskAssign)]
    assert [message.x for message in assignments] == [9.0, 1.0]


# ─────────────────────────────────────────────────────────────────────────────
def test_batch_cancel_runs_before_assignment() -> None:
    """Kiểm tra cancel giải phóng robot trước khi dispatcher thử assign mới."""
    uart = FakeUart()
    dispatcher = RobotDispatcherV2(uart)
    dispatcher.on_heartbeat(_heartbeat())
    current = _zone("current")
    waiting = _zone("waiting", priority=ZonePriority.HIGH)
    assert dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, current),
    )
    uart.sent.clear()

    assert dispatcher.process_decisions([
        _decision(DispatchAction.TASK_ASSIGN, waiting),
        _decision(DispatchAction.TASK_CANCEL, current),
    ]) == [True, True]

    assert [type(message) for message in uart.sent] == [TaskCancel, TaskAssign]
    assert _assigned_task_for_zone(dispatcher, waiting.id) is not None


# ─────────────────────────────────────────────────────────────────────────────
def test_high_priority_does_not_preempt_assigned_task() -> None:
    """Kiểm tra task priority cao không tự hủy task đã giao cho robot."""
    uart = FakeUart()
    dispatcher = RobotDispatcherV2(uart)
    dispatcher.on_heartbeat(_heartbeat())
    low = _zone("low", priority=ZonePriority.LOW)
    high = _zone("high", priority=ZonePriority.HIGH)
    assert dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, low),
    )
    uart.sent.clear()

    assert not dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, high),
    )

    assert _assigned_task_for_zone(dispatcher, low.id) is not None
    assert _assigned_task_for_zone(dispatcher, high.id) is None
    assert not any(isinstance(message, TaskCancel) for message in uart.sent)


# ─────────────────────────────────────────────────────────────────────────────
def test_completed_status_is_idempotent_and_acknowledged() -> None:
    uart = FakeUart()
    engine = DispatchDecisionEngine()
    dispatcher = RobotDispatcherV2(
        uart,
        decision_engine=engine,
    )
    dispatcher.on_heartbeat(_heartbeat())
    zone = _zone("zone-1", state=ZoneState.PENDING_ENTER)

    dispatcher.process_zones([zone])
    zone.state = ZoneState.OCCUPIED
    dispatcher.process_zones([zone])
    task = _assigned_task_for_zone(dispatcher, zone.id)
    assert task is not None

    status = TaskStatus(
        robot_id=task.robot_id,
        task_id=task.task_id,
        status_code=TaskStatusCode.COMPLETED,
    )
    dispatcher.on_task_status(status)
    dispatcher.on_task_status(status)

    assert _assigned_task_for_zone(dispatcher, zone.id) is None
    assert engine.get_service_state(zone.id) is ZoneServiceState.COMPLETED
    assert len([message for message in uart.sent if isinstance(message, Ack)]) == 2


# ─────────────────────────────────────────────────────────────────────────────
def test_failed_status_marks_service_failed_until_zone_is_empty() -> None:
    uart = FakeUart()
    engine = DispatchDecisionEngine()
    dispatcher = RobotDispatcherV2(uart, decision_engine=engine)
    dispatcher.on_heartbeat(_heartbeat())
    zone = _zone("zone-1", state=ZoneState.PENDING_ENTER)

    dispatcher.process_zones([zone])
    zone.state = ZoneState.OCCUPIED
    dispatcher.process_zones([zone])
    task = _assigned_task_for_zone(dispatcher, zone.id)
    assert task is not None

    dispatcher.on_task_status(
        TaskStatus(
            robot_id=task.robot_id,
            task_id=task.task_id,
            status_code=TaskStatusCode.FAILED,
        )
    )
    assert _assigned_task_for_zone(dispatcher, zone.id) is None
    assert engine.get_service_state(zone.id) is ZoneServiceState.FAILED

    zone.state = ZoneState.PENDING_EXIT
    assert dispatcher.process_zones([zone]) == []
    zone.state = ZoneState.EMPTY
    assert dispatcher.process_zones([zone]) == []
    assert engine.get_service_state(zone.id) is ZoneServiceState.NOT_REQUESTED


# ─────────────────────────────────────────────────────────────────────────────
def test_failed_status_exposes_robot_failure_reason() -> None:
    """TaskStatus FAILED lưu mã lỗi robot vào read-model dùng bởi API/WS."""
    uart = FakeUart()
    activity_store = TaskActivityStore()
    dispatcher = RobotDispatcherV2(
        uart,
        task_activity_store=activity_store,
    )
    dispatcher.on_heartbeat(_heartbeat())
    zone = _zone("zone-blocked")
    assert dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, zone)
    )
    task = _assigned_task_for_zone(dispatcher, zone.id)
    assert task is not None

    dispatcher.on_task_status(
        TaskStatus(
            robot_id=task.robot_id,
            task_id=task.task_id,
            status_code=TaskStatusCode.FAILED,
            reason_code=TaskFailureReasonCode.PATH_BLOCKED,
        )
    )

    failed = activity_store.snapshot()["tasks"][0]
    assert failed["status"] == "FAILED"
    assert failed["failure_reason"] == "PATH_BLOCKED"
    assert failed["failure_reason_code"] == TaskFailureReasonCode.PATH_BLOCKED


# ─────────────────────────────────────────────────────────────────────────────
def test_invalid_goal_pose_rolls_back_requested_service() -> None:
    uart = FakeUart()
    engine = DispatchDecisionEngine()
    dispatcher = RobotDispatcherV2(uart, decision_engine=engine)
    dispatcher.on_heartbeat(_heartbeat())
    zone = _zone(
        "zone-1",
        state=ZoneState.PENDING_ENTER,
        goal_pose={"x": 1.0},
    )

    dispatcher.process_zones([zone])
    zone.state = ZoneState.OCCUPIED
    dispatcher.process_zones([zone])

    assert dispatcher.pending_count() == 0
    assert _assigned_task_for_zone(dispatcher, zone.id) is None
    assert engine.get_service_state(zone.id) is ZoneServiceState.NOT_REQUESTED


# ─────────────────────────────────────────────────────────────────────────────
def test_dispatcher_subscribes_without_replacing_existing_handler() -> None:
    uart = FakeUart()
    received = []
    uart.set_handler(MessageType.HEARTBEAT, received.append)
    dispatcher = RobotDispatcherV2(uart)
    heartbeat = _heartbeat()

    uart.emit(heartbeat)

    assert received == [heartbeat]
    assert dispatcher.robot_state_store.get(heartbeat.robot_id) is not None


# ─────────────────────────────────────────────────────────────────────────────
def test_dispatcher_can_use_externally_managed_heartbeat_store() -> None:
    uart = FakeUart()
    dispatcher = RobotDispatcherV2(
        uart,
        register_heartbeat_handler=False,
    )

    assert int(MessageType.HEARTBEAT) not in uart.additional_handlers
    assert int(MessageType.TASK_STATUS) in uart.additional_handlers

    uart.emit(_heartbeat())

    assert dispatcher.robot_state_store.all_snapshots() == []


# ─────────────────────────────────────────────────────────────────────────────
def test_close_removes_only_dispatcher_subscribers() -> None:
    uart = FakeUart()
    received = []
    uart.set_handler(MessageType.HEARTBEAT, received.append)
    dispatcher = RobotDispatcherV2(uart)

    dispatcher.close()
    heartbeat = _heartbeat(robot_id=2)
    uart.emit(heartbeat)

    assert received == [heartbeat]
    assert dispatcher.robot_state_store.get(heartbeat.robot_id) is None


# ─────────────────────────────────────────────────────────────────────────────
def test_person_request_is_released_only_after_cancel_succeeds() -> None:
    uart = FakeUart()
    uart.set_outcomes(TaskCancel, False, True)
    engine = DispatchDecisionEngine(policy=ReIdDecisionPolicy())
    dispatcher = RobotDispatcherV2(
        uart,
        decision_engine=engine,
        retry_backoff_seconds=0,
    )
    zone = _zone("zone-1", state=ZoneState.PENDING_ENTER)
    person = Detection(
        bbox=(0.0, 0.0, 10.0, 20.0),
        confidence=0.95,
        track_id=10,
        global_id=42,
        similarity=0.9,
    )
    uart.emit(_heartbeat())

    engine.process_zones([zone])
    zone.state = ZoneState.OCCUPIED
    assign_decisions = engine.process_zones(
        [zone],
        detections=[person],
        zone_names=[zone.name],
    )
    assert dispatcher.process_decisions(assign_decisions) == [True]

    zone.state = ZoneState.PENDING_EXIT
    assert engine.process_zones([zone]) == []
    zone.state = ZoneState.EMPTY
    cancel_decisions = engine.process_zones([zone])
    assert dispatcher.process_decisions(cancel_decisions) == [False]

    assert engine.get_service_state(zone.id) is ZoneServiceState.CANCEL_REQUESTED
    assert engine.get_person_service_state(42) is PersonServiceState.REQUESTED

    assert dispatcher.tick() == 1
    assert engine.get_service_state(zone.id) is ZoneServiceState.NOT_REQUESTED
    assert engine.get_person_service_state(42) is None


# ────────────────────────────────────────────────────────────────────
def test_process_zones_forwards_reid_inputs_to_decision_engine() -> None:
    uart = FakeUart()
    engine = DispatchDecisionEngine(policy=ReIdDecisionPolicy())
    dispatcher = RobotDispatcherV2(uart, decision_engine=engine)
    zone = _zone(
        "zone-1",
        state=ZoneState.PENDING_ENTER,
        priority=ZonePriority.HIGH,
    )
    person = Detection(
        bbox=(0.0, 0.0, 10.0, 20.0),
        confidence=0.95,
        track_id=10,
        global_id=42,
        similarity=0.9,
    )
    uart.emit(_heartbeat())

    assert dispatcher.process_zones([zone]) == []
    zone.state = ZoneState.OCCUPIED
    decisions = dispatcher.process_zones(
        [zone],
        detections=[person],
        zone_names=[zone.name],
    )

    assert [decision.action for decision in decisions] == [
        DispatchAction.TASK_ASSIGN
    ]
    assert decisions[0].person_global_id == 42
    assert decisions[0].priority is ZonePriority.HIGH
    assert _assigned_task_for_zone(dispatcher, zone.id) is not None


# ─────────────────────────────────────────────────────────────────────────────
def test_task_activity_keeps_terminal_task_history() -> None:
    """Kiểm tra read-model giữ task terminal trong lịch sử runtime."""
    uart = FakeUart()
    activity_store = TaskActivityStore()
    dispatcher = RobotDispatcherV2(
        uart,
        task_activity_store=activity_store,
    )
    dispatcher.on_heartbeat(_heartbeat())
    zone = _zone(
        "zone-1",
        priority=ZonePriority.HIGH,
        service_point=(123.4, 567.6),
    )

    assert dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, zone)
    )
    assigned = activity_store.snapshot()["tasks"][0]
    assert assigned["status"] == "ASSIGNED"
    assert assigned["robot_id"] == 1
    assert assigned["task_id"] == 0
    assert assigned["camera_id"] == "camera-1"
    assert assigned["zone_name"] == "zone-1"
    assert assigned["origin"] == "zone"
    assert assigned["priority"] == "high"
    assert assigned["target_pixel"] == {"x": 123, "y": 568}
    assert assigned["goal_pose"] == {"x": 1.0, "y": 2.0, "theta": 0.0}

    dispatcher.on_task_status(
        TaskStatus(
            robot_id=1,
            task_id=0,
            status_code=TaskStatusCode.IN_PROGRESS,
        )
    )
    assert activity_store.snapshot()["tasks"][0]["status"] == "IN_PROGRESS"

    dispatcher.on_task_status(
        TaskStatus(
            robot_id=1,
            task_id=0,
            status_code=TaskStatusCode.COMPLETED,
        )
    )
    snapshot = activity_store.snapshot()
    assert snapshot["active"] == 0
    assert snapshot["completed"] == 1
    assert snapshot["tasks"][0]["status"] == "COMPLETED"
    assert snapshot["tasks"][0]["completed_at"] is not None


# ─────────────────────────────────────────────────────────────────────────────
def test_task_activity_tracks_assign_retry_and_cancel() -> None:
    """Kiểm tra read-model theo dõi retry assign và trạng thái hủy."""
    uart = FakeUart()
    uart.set_outcomes(TaskAssign, False, True)
    activity_store = TaskActivityStore()
    dispatcher = RobotDispatcherV2(
        uart,
        task_activity_store=activity_store,
        retry_backoff_seconds=0,
    )
    dispatcher.on_heartbeat(_heartbeat())
    zone = _zone("zone-1")

    assert not dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, zone)
    )
    first_snapshot = activity_store.snapshot()
    assert first_snapshot["tasks"][0]["status"] == "ASSIGNING"
    assert first_snapshot["tasks"][0]["retry_count"] == 1

    assert dispatcher.tick() == 1
    assert activity_store.snapshot()["tasks"][0]["status"] == "ASSIGNED"

    assert dispatcher.process_decision(
        _decision(DispatchAction.TASK_CANCEL, zone)
    )
    snapshot = activity_store.snapshot()
    assert snapshot["canceled"] == 1
    assert snapshot["tasks"][0]["status"] == "CANCELED"


# ─────────────────────────────────────────────────────────────────────────────
def test_background_ack_returns_before_uart_ack_is_received() -> None:
    """Kiểm tra dispatch nền không chặn caller khi UART đang chờ ACK."""
    uart = BlockingAckUart()
    dispatcher = RobotDispatcherV2(uart, background_ack=True)
    zone = _zone("zone-1")
    dispatcher.on_heartbeat(_heartbeat())

    try:
        started_at = time.monotonic()
        handled = dispatcher.process_decision(
            _decision(DispatchAction.TASK_ASSIGN, zone)
        )
        elapsed = time.monotonic() - started_at

        assert not handled
        assert elapsed < 0.1
        assert uart.started.wait(timeout=1.0)
        assert dispatcher.pending_count() == 1

        uart.release.set()
        deadline = time.monotonic() + 1.0
        while dispatcher.pending_count() != 0 and time.monotonic() < deadline:
            time.sleep(0.01)

        assert dispatcher.pending_count() == 0
        assert _assigned_task_for_zone(dispatcher, zone.id) is not None
    finally:
        uart.release.set()
        dispatcher.close()


# ─────────────────────────────────────────────────────────────────────────────
def test_cancel_while_assign_ack_is_pending_finishes_after_assign() -> None:
    """Cancel trong lúc chờ ACK assign được giữ lại và gửi ngay sau ACK."""
    uart = BlockingAckUart()
    activity_store = TaskActivityStore()
    dispatcher = RobotDispatcherV2(
        uart,
        task_activity_store=activity_store,
        background_ack=True,
    )
    dispatcher.on_heartbeat(_heartbeat())

    try:
        task_uid = dispatcher.enqueue_manual_task(
            camera_id="camera-1",
            camera_name="Camera 1",
            target_pixel=(100.0, 200.0),
            goal_pose={"x": 1.0, "y": 2.0, "theta": 0.0},
            priority=TaskPriority.HIGH,
        )
        assert uart.started.wait(timeout=1.0)
        assert not dispatcher.cancel_task(task_uid)
        assert activity_store.get(task_uid).status == "CANCELING"

        uart.release.set()
        deadline = time.monotonic() + 1.0
        while dispatcher.pending_count() != 0 and time.monotonic() < deadline:
            time.sleep(0.01)

        assert dispatcher.pending_count() == 0
        assert activity_store.get(task_uid).status == "CANCELED"
        assert [type(message) for message in uart.sent] == [TaskAssign, TaskCancel]
    finally:
        uart.release.set()
        dispatcher.close()
