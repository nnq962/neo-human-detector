import numpy as np

from src.dispatch_decision import (
    DispatchAction,
    DispatchDecisionEngine,
    ZoneServiceState,
)
from src.zones_management import Zone, ZoneState


# ─────────────────────────────────────────────────────────────────────────────
def _zone(state: ZoneState = ZoneState.EMPTY) -> Zone:
    """Tạo zone tối giản phục vụ test decision engine."""
    return Zone(
        camera_id="camera-1",
        camera_name="Camera 1",
        id="zone-1",
        name="Zone 1",
        pts=np.empty((0, 2), dtype=np.int32),
        goal_pose={"x": 1.0, "y": 2.0, "theta": 0.0},
        state=state,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _open_service(engine: DispatchDecisionEngine, zone: Zone) -> None:
    """Đưa zone qua transition xác nhận vào và tạo yêu cầu phục vụ."""
    engine.process_zones([zone])
    zone.state = ZoneState.OCCUPIED
    decisions = engine.process_zones([zone])
    assert [decision.action for decision in decisions] == [DispatchAction.TASK_ASSIGN]


# ─────────────────────────────────────────────────────────────────────────────
def test_assign_only_on_pending_enter_to_occupied() -> None:
    zone = _zone()
    engine = DispatchDecisionEngine()

    assert engine.process_zones([zone]) == []
    zone.state = ZoneState.PENDING_ENTER
    assert engine.process_zones([zone]) == []
    zone.state = ZoneState.OCCUPIED

    decisions = engine.process_zones([zone])

    assert [decision.action for decision in decisions] == [DispatchAction.TASK_ASSIGN]
    assert engine.has_requested_service(zone.id)


# ─────────────────────────────────────────────────────────────────────────────
def test_does_not_assign_twice_during_same_occupancy() -> None:
    zone = _zone(ZoneState.PENDING_ENTER)
    engine = DispatchDecisionEngine()
    _open_service(engine, zone)

    assert engine.process_zones([zone]) == []
    zone.state = ZoneState.PENDING_EXIT
    assert engine.process_zones([zone]) == []
    zone.state = ZoneState.OCCUPIED
    assert engine.process_zones([zone]) == []


# ─────────────────────────────────────────────────────────────────────────────
def test_empty_cancels_requested_service() -> None:
    zone = _zone(ZoneState.PENDING_ENTER)
    engine = DispatchDecisionEngine()
    _open_service(engine, zone)
    zone.state = ZoneState.PENDING_EXIT
    assert engine.process_zones([zone]) == []
    zone.state = ZoneState.EMPTY

    decisions = engine.process_zones([zone])

    assert [decision.action for decision in decisions] == [DispatchAction.TASK_CANCEL]
    assert engine.get_service_state(zone.id) is ZoneServiceState.NOT_REQUESTED


# ─────────────────────────────────────────────────────────────────────────────
def test_empty_does_not_cancel_completed_service() -> None:
    zone = _zone(ZoneState.PENDING_ENTER)
    engine = DispatchDecisionEngine()
    _open_service(engine, zone)
    assert engine.on_service_completed(zone.id)
    zone.state = ZoneState.PENDING_EXIT
    assert engine.process_zones([zone]) == []
    zone.state = ZoneState.EMPTY

    assert engine.process_zones([zone]) == []
    assert engine.get_service_state(zone.id) is ZoneServiceState.NOT_REQUESTED

    zone.state = ZoneState.PENDING_ENTER
    assert engine.process_zones([zone]) == []
    zone.state = ZoneState.OCCUPIED
    assert [
        decision.action for decision in engine.process_zones([zone])
    ] == [DispatchAction.TASK_ASSIGN]


# ─────────────────────────────────────────────────────────────────────────────
def test_completion_during_pending_exit_prevents_cancel() -> None:
    zone = _zone(ZoneState.PENDING_ENTER)
    engine = DispatchDecisionEngine()
    _open_service(engine, zone)
    zone.state = ZoneState.PENDING_EXIT
    engine.process_zones([zone])

    assert engine.on_service_completed(zone.id)
    zone.state = ZoneState.EMPTY

    assert engine.process_zones([zone]) == []


# ─────────────────────────────────────────────────────────────────────────────
def test_other_transitions_do_not_emit_decisions() -> None:
    zone = _zone()
    engine = DispatchDecisionEngine()
    engine.process_zones([zone])

    for state in (
        ZoneState.OCCUPIED,
        ZoneState.PENDING_EXIT,
        ZoneState.OCCUPIED,
        ZoneState.EMPTY,
        ZoneState.PENDING_ENTER,
        ZoneState.EMPTY,
    ):
        zone.state = state
        assert engine.process_zones([zone]) == []


# ─────────────────────────────────────────────────────────────────────────────
def test_failed_service_is_terminal_until_zone_becomes_empty() -> None:
    zone = _zone(ZoneState.PENDING_ENTER)
    engine = DispatchDecisionEngine()
    _open_service(engine, zone)

    assert engine.on_service_failed(zone.id)
    assert engine.get_service_state(zone.id) is ZoneServiceState.FAILED
    assert engine.process_zones([zone]) == []

    zone.state = ZoneState.PENDING_EXIT
    assert engine.process_zones([zone]) == []
    zone.state = ZoneState.EMPTY
    assert engine.process_zones([zone]) == []
    assert engine.get_service_state(zone.id) is ZoneServiceState.NOT_REQUESTED


# ─────────────────────────────────────────────────────────────────────────────
def test_request_failure_rolls_back_requested_state() -> None:
    zone = _zone(ZoneState.PENDING_ENTER)
    engine = DispatchDecisionEngine()
    _open_service(engine, zone)

    assert engine.on_service_request_failed(zone.id)
    assert engine.get_service_state(zone.id) is ZoneServiceState.NOT_REQUESTED
