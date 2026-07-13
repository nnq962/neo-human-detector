import time

import numpy as np

from src.dispatch_decision import DispatchAction, DispatchDecision
from src.robot_dispatch_v2 import RobotDispatcherV2, TaskRegistry, TaskRegistryFull
from src.robot_dispatch_v2.datatypes import (
    Ack,
    Heartbeat,
    RobotStateCode,
    TaskAssign,
    TaskCancel,
    TaskStatus,
    TaskStatusCode,
)
from src.zones_management import Zone, ZoneState


# ─────────────────────────────────────────────────────────────────────────────
class FakeUart:
    """UART giả cho phép cấu hình kết quả gửi theo loại message."""

    def __init__(self) -> None:
        self.sent = []
        self.outcomes = {}

    def set_outcomes(self, message_class, *outcomes: bool) -> None:
        self.outcomes[message_class] = list(outcomes)

    def send_with_retry(self, message, task_id: int) -> bool:
        self.sent.append(message)
        outcomes = self.outcomes.get(type(message), [])
        return outcomes.pop(0) if outcomes else True

    def send_message(self, message) -> bool:
        self.sent.append(message)
        return True


# ─────────────────────────────────────────────────────────────────────────────
class FakeLifecycleSink:
    """Ghi lại feedback lifecycle do dispatcher phát."""

    def __init__(self) -> None:
        self.events = []

    def on_service_started(self, zone_id, person_id, *, timestamp=None) -> None:
        self.events.append(("started", zone_id, person_id))

    def on_service_completed(self, zone_id, person_id, *, timestamp=None) -> None:
        self.events.append(("completed", zone_id, person_id))

    def on_service_cancelled(self, zone_id, person_id, *, timestamp=None) -> None:
        self.events.append(("cancelled", zone_id, person_id))

    def on_service_failed(self, zone_id, person_id, *, timestamp=None) -> None:
        self.events.append(("failed", zone_id, person_id))


# ─────────────────────────────────────────────────────────────────────────────
class FlakyTaskRegistry(TaskRegistry):
    """Registry giả hết task_id ở lần allocate đầu tiên."""

    def __init__(self) -> None:
        super().__init__()
        self.fail_next_allocate = True

    def allocate(self, robot_id: int, zone_id: str, person_global_id=None) -> int:
        if self.fail_next_allocate:
            self.fail_next_allocate = False
            raise TaskRegistryFull(robot_id)
        return super().allocate(robot_id, zone_id, person_global_id)


# ─────────────────────────────────────────────────────────────────────────────
def _zone(zone_id: str, x: float = 1.0) -> Zone:
    return Zone(
        camera_id="camera-1",
        camera_name="Camera 1",
        id=zone_id,
        name=zone_id,
        pts=np.empty((0, 2), dtype=np.int32),
        goal_pose={"x": x, "y": 2.0, "theta": 0.0},
        state=ZoneState.OCCUPIED,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _decision(
    action: DispatchAction,
    zone: Zone,
    person_id=None,
    previous_person_id=None,
) -> DispatchDecision:
    return DispatchDecision(
        action=action,
        zone_id=str(zone.id or zone.key),
        zone=zone,
        previous_state=ZoneState.PENDING_ENTER,
        current_state=zone.state,
        person_id=person_id,
        previous_person_id=previous_person_id,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _dispatcher(
    *,
    uart=None,
    registry=None,
    sink=None,
) -> RobotDispatcherV2:
    dispatcher = RobotDispatcherV2(
        uart or FakeUart(),
        task_registry=registry,
        service_lifecycle_sink=sink,
    )
    dispatcher.on_heartbeat(
        Heartbeat(
            robot_id=1,
            timestamp=int(time.time()),
            x=0.0,
            y=0.0,
            theta=0.0,
            state_code=RobotStateCode.IDLE,
        )
    )
    return dispatcher


# ─────────────────────────────────────────────────────────────────────────────
def test_robot_reservation_prevents_double_assign_until_terminal_status() -> None:
    uart = FakeUart()
    dispatcher = _dispatcher(uart=uart)
    zone_a = _zone("zone-a")
    zone_b = _zone("zone-b")

    dispatcher.process_decision(_decision(DispatchAction.REQUEST_SERVICE, zone_a, 7))
    dispatcher.process_decision(_decision(DispatchAction.REQUEST_SERVICE, zone_b, 9))

    task_a = dispatcher.get_assigned_task("zone-a")
    assert task_a is not None
    assert dispatcher.get_assigned_task("zone-b") is None

    dispatcher.on_task_status(
        TaskStatus(task_a.robot_id, task_a.task_id, TaskStatusCode.COMPLETED)
    )
    dispatcher.tick()

    assert dispatcher.get_assigned_task("zone-b") is not None
    assert any(isinstance(message, Ack) for message in uart.sent)


# ─────────────────────────────────────────────────────────────────────────────
def test_cancel_failure_keeps_task_and_retries_on_tick() -> None:
    uart = FakeUart()
    uart.set_outcomes(TaskCancel, False, True)
    sink = FakeLifecycleSink()
    dispatcher = _dispatcher(uart=uart, sink=sink)
    zone = _zone("zone-1")
    dispatcher.process_decision(_decision(DispatchAction.REQUEST_SERVICE, zone, 7))

    dispatcher.process_decision(_decision(DispatchAction.ZONE_CLEARED, zone, 7))

    assert dispatcher.get_assigned_task(zone.id) is not None
    assert dispatcher.pending_count() == 1

    dispatcher.tick()

    assert dispatcher.get_assigned_task(zone.id) is None
    assert dispatcher.pending_count() == 0
    assert ("cancelled", zone.id, 7) in sink.events


# ─────────────────────────────────────────────────────────────────────────────
def test_cancel_with_stale_person_does_not_cancel_newer_task() -> None:
    uart = FakeUart()
    dispatcher = _dispatcher(uart=uart)
    zone = _zone("zone-1")
    dispatcher.process_decision(_decision(DispatchAction.REQUEST_SERVICE, zone, 9))

    handled = dispatcher.process_decision(
        _decision(DispatchAction.CANCEL_SERVICE, zone, person_id=7)
    )

    assert not handled
    assert dispatcher.get_assigned_task(zone.id).person_global_id == 9
    assert not any(isinstance(message, TaskCancel) for message in uart.sent)


# ─────────────────────────────────────────────────────────────────────────────
def test_replace_cancels_old_task_before_assigning_new_task() -> None:
    uart = FakeUart()
    sink = FakeLifecycleSink()
    dispatcher = _dispatcher(uart=uart, sink=sink)
    zone = _zone("zone-1")
    dispatcher.process_decision(_decision(DispatchAction.REQUEST_SERVICE, zone, 7))

    dispatcher.process_decision(
        _decision(
            DispatchAction.REPLACE_SERVICE,
            zone,
            person_id=9,
            previous_person_id=7,
        )
    )

    assert [type(message) for message in uart.sent] == [TaskAssign, TaskCancel, TaskAssign]
    assert dispatcher.get_assigned_task(zone.id).person_global_id == 9
    assert ("cancelled", zone.id, 7) in sink.events


# ─────────────────────────────────────────────────────────────────────────────
def test_zone_cleared_drops_replacement_and_cancels_actual_old_task() -> None:
    uart = FakeUart()
    uart.set_outcomes(TaskCancel, False, True)
    dispatcher = _dispatcher(uart=uart)
    zone = _zone("zone-1")
    dispatcher.process_decision(_decision(DispatchAction.REQUEST_SERVICE, zone, 7))
    dispatcher.process_decision(
        _decision(
            DispatchAction.REPLACE_SERVICE,
            zone,
            person_id=9,
            previous_person_id=7,
        )
    )

    dispatcher.process_decision(_decision(DispatchAction.ZONE_CLEARED, zone, 9))

    assert dispatcher.get_assigned_task(zone.id) is None
    assert dispatcher.pending_count() == 0
    assert [type(message) for message in uart.sent] == [TaskAssign, TaskCancel, TaskCancel]


# ─────────────────────────────────────────────────────────────────────────────
def test_task_status_emits_started_and_completed_feedback() -> None:
    uart = FakeUart()
    sink = FakeLifecycleSink()
    dispatcher = _dispatcher(uart=uart, sink=sink)
    zone = _zone("zone-1")
    dispatcher.process_decision(_decision(DispatchAction.REQUEST_SERVICE, zone, 7))
    task = dispatcher.get_assigned_task(zone.id)

    dispatcher.on_task_status(
        TaskStatus(task.robot_id, task.task_id, TaskStatusCode.IN_PROGRESS)
    )
    dispatcher.on_task_status(
        TaskStatus(task.robot_id, task.task_id, TaskStatusCode.COMPLETED)
    )

    assert sink.events == [
        ("started", zone.id, 7),
        ("completed", zone.id, 7),
    ]
    assert dispatcher.get_assigned_task(zone.id) is None
    assert len([message for message in uart.sent if isinstance(message, Ack)]) == 2


# ─────────────────────────────────────────────────────────────────────────────
def test_task_registry_full_keeps_request_for_next_tick() -> None:
    uart = FakeUart()
    dispatcher = _dispatcher(uart=uart, registry=FlakyTaskRegistry())
    zone = _zone("zone-1")

    dispatcher.process_decision(_decision(DispatchAction.REQUEST_SERVICE, zone, 7))

    assert dispatcher.get_assigned_task(zone.id) is None
    assert dispatcher.pending_count() == 1

    dispatcher.tick()

    assert dispatcher.get_assigned_task(zone.id) is not None
    assert dispatcher.pending_count() == 0


# ─────────────────────────────────────────────────────────────────────────────
def test_zone_without_explicit_id_uses_stable_zone_key() -> None:
    dispatcher = _dispatcher()
    zone = _zone("temporary")
    zone.id = None

    dispatcher.process_decision(_decision(DispatchAction.REQUEST_SERVICE, zone, 7))

    assert dispatcher.get_assigned_task(zone.key) is not None
