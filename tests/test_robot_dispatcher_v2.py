import time

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
    TaskStatus,
    TaskStatusCode,
)
from src.zones_management import Zone, ZoneState


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


# ─────────────────────────────────────────────────────────────────────────────
def _zone(
    zone_id: str,
    *,
    state: ZoneState = ZoneState.OCCUPIED,
    goal_pose=None,
) -> Zone:
    return Zone(
        camera_id="camera-1",
        camera_name="Camera 1",
        id=zone_id,
        name=zone_id,
        pts=np.empty((0, 2), dtype=np.int32),
        goal_pose=goal_pose or {"x": 1.0, "y": 2.0, "theta": 0.0},
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
def test_lost_assign_ack_retries_same_robot_and_task() -> None:
    uart = FakeUart()
    uart.set_outcomes(TaskAssign, False, True)
    dispatcher = RobotDispatcherV2(uart)
    dispatcher.on_heartbeat(_heartbeat())
    zone = _zone("zone-1")

    assert not dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, zone)
    )
    reserved = dispatcher.get_assigned_task(zone.id)
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
def test_new_assign_waits_for_pending_cancel_of_old_task() -> None:
    uart = FakeUart()
    uart.set_outcomes(TaskCancel, False, True)
    dispatcher = RobotDispatcherV2(uart)
    dispatcher.on_heartbeat(_heartbeat())
    zone = _zone("zone-1")

    assert dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, zone)
    )
    old_task = dispatcher.get_assigned_task(zone.id)
    assert old_task is not None

    assert not dispatcher.process_decision(
        _decision(DispatchAction.TASK_CANCEL, zone)
    )
    assert not dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, zone)
    )
    assert dispatcher.pending_count() == 2

    assert dispatcher.tick() == 2
    new_task = dispatcher.get_assigned_task(zone.id)
    assert new_task is not None
    assert new_task.task_id != old_task.task_id
    assert [type(message) for message in uart.sent] == [
        TaskAssign,
        TaskCancel,
        TaskCancel,
        TaskAssign,
    ]


# ─────────────────────────────────────────────────────────────────────────────
def test_existing_reservation_is_bound_and_sent_instead_of_dropped() -> None:
    uart = FakeUart()
    registry = TaskRegistry()
    reserved = registry.allocate(robot_id=1, zone_id="zone-1")
    dispatcher = RobotDispatcherV2(uart, task_registry=registry)
    zone = _zone("zone-1")

    assert dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, zone)
    )

    assert len(uart.sent) == 1
    assert isinstance(uart.sent[0], TaskAssign)
    assert uart.sent[0].robot_id == reserved.robot_id
    assert uart.sent[0].task_id == reserved.task_id
    assert dispatcher.pending_count() == 0


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
    assert dispatcher.get_assigned_task(zone.id) is not None


# ─────────────────────────────────────────────────────────────────────────────
def test_completed_status_is_idempotent_and_acknowledged() -> None:
    uart = FakeUart()
    engine = DispatchDecisionEngine()
    dispatcher = RobotDispatcherV2(uart, decision_engine=engine)
    dispatcher.on_heartbeat(_heartbeat())
    zone = _zone("zone-1", state=ZoneState.PENDING_ENTER)

    dispatcher.process_zones([zone])
    zone.state = ZoneState.OCCUPIED
    dispatcher.process_zones([zone])
    task = dispatcher.get_assigned_task(zone.id)
    assert task is not None

    status = TaskStatus(
        robot_id=task.robot_id,
        task_id=task.task_id,
        status_code=TaskStatusCode.COMPLETED,
    )
    dispatcher.on_task_status(status)
    dispatcher.on_task_status(status)

    assert dispatcher.get_assigned_task(zone.id) is None
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
    task = dispatcher.get_assigned_task(zone.id)
    assert task is not None

    dispatcher.on_task_status(
        TaskStatus(
            robot_id=task.robot_id,
            task_id=task.task_id,
            status_code=TaskStatusCode.FAILED,
        )
    )
    assert dispatcher.get_assigned_task(zone.id) is None
    assert engine.get_service_state(zone.id) is ZoneServiceState.FAILED

    zone.state = ZoneState.PENDING_EXIT
    assert dispatcher.process_zones([zone]) == []
    zone.state = ZoneState.EMPTY
    assert dispatcher.process_zones([zone]) == []
    assert engine.get_service_state(zone.id) is ZoneServiceState.NOT_REQUESTED


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
    assert dispatcher.get_assigned_task(zone.id) is None
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
    dispatcher = RobotDispatcherV2(uart, decision_engine=engine)
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
    zone = _zone("zone-1", state=ZoneState.PENDING_ENTER)
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
    assert dispatcher.get_assigned_task(zone.id) is not None


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
    zone = _zone("zone-1")

    assert dispatcher.process_decision(
        _decision(DispatchAction.TASK_ASSIGN, zone)
    )
    assigned = activity_store.snapshot()["tasks"][0]
    assert assigned["status"] == "ASSIGNED"
    assert assigned["robot_id"] == 1
    assert assigned["task_id"] == 0
    assert assigned["camera_id"] == "camera-1"
    assert assigned["zone_name"] == "zone-1"
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
