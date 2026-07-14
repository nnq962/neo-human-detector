import numpy as np

from src.detection import Detection
from src.dispatch_decision import (
    DispatchAction,
    DispatchDecisionEngine,
    PersonServiceState,
    ReIdDecisionPolicy,
    ZoneServiceState,
)
from src.zones_management import Zone, ZoneState


# ─────────────────────────────────────────────────────────────────────────────
def _zone(
    zone_id: str,
    name: str,
    state: ZoneState = ZoneState.PENDING_ENTER,
) -> Zone:
    """Tạo zone tối giản phục vụ kiểm thử decision có ReID."""
    return Zone(
        camera_id="camera-1",
        camera_name="Camera 1",
        id=zone_id,
        name=name,
        pts=np.empty((0, 2), dtype=np.int32),
        goal_pose={"x": 1.0, "y": 2.0, "theta": 0.0},
        state=state,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _person(
    global_id: int,
    *,
    similarity: float = 0.9,
    track_id: int = 10,
) -> Detection:
    """Tạo detection đã được ReID gắn identity."""
    return Detection(
        bbox=(0.0, 0.0, 10.0, 20.0),
        confidence=0.95,
        track_id=track_id,
        global_id=global_id,
        similarity=similarity,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _reid_engine() -> DispatchDecisionEngine:
    """Tạo decision engine đã bật policy ReID."""
    return DispatchDecisionEngine(
        policy=ReIdDecisionPolicy(),
    )


# ─────────────────────────────────────────────────────────────────────────────
def _open_reid_service(
    engine: DispatchDecisionEngine,
    zone: Zone,
    person: Detection,
):
    """Đưa zone sang OCCUPIED và trả TASK_ASSIGN cho người đã chọn."""
    engine.process_zones([zone])
    zone.state = ZoneState.OCCUPIED
    decisions = engine.process_zones(
        [zone],
        detections=[person],
        zone_names=[zone.name],
    )
    assert len(decisions) == 1
    return decisions[0]


# ─────────────────────────────────────────────────────────────────────────────
def test_identity_appearing_after_pending_exit_emits_one_assign() -> None:
    zone = _zone("zone-1", "Zone 1")
    person = _person(42, similarity=0.91, track_id=17)
    engine = _reid_engine()

    engine.process_zones([zone])
    zone.state = ZoneState.OCCUPIED
    assert engine.process_zones([zone]) == []
    assert engine.is_awaiting_identity(zone.id)

    zone.state = ZoneState.PENDING_EXIT
    assert engine.process_zones([zone]) == []
    assert engine.is_awaiting_identity(zone.id)

    zone.state = ZoneState.OCCUPIED
    decisions = engine.process_zones(
        [zone],
        detections=[person],
        zone_names=[zone.name],
    )

    assert len(decisions) == 1
    assert decisions[0].action is DispatchAction.TASK_ASSIGN
    assert decisions[0].person_global_id == 42
    assert decisions[0].person_similarity == 0.91
    assert decisions[0].person_track_id == 17
    assert not engine.is_awaiting_identity(zone.id)
    assert engine.get_person_service_state(42) is PersonServiceState.REQUESTED

    assert engine.process_zones(
        [zone],
        detections=[person],
        zone_names=[zone.name],
    ) == []


# ─────────────────────────────────────────────────────────────────────────────
def test_completed_person_is_blocked_in_every_zone() -> None:
    first_zone = _zone("zone-1", "Zone 1")
    second_zone = _zone("zone-2", "Zone 2")
    person = _person(42)
    engine = _reid_engine()

    _open_reid_service(engine, first_zone, person)
    assert engine.on_service_completed(first_zone.id)
    assert engine.has_person_been_served(42)

    engine.process_zones([second_zone])
    second_zone.state = ZoneState.OCCUPIED
    decisions = engine.process_zones(
        [second_zone],
        detections=[person],
        zone_names=[second_zone.name],
    )

    assert decisions == []
    assert engine.has_person_been_served(42)


# ─────────────────────────────────────────────────────────────────────────────
def test_cancel_releases_person_only_after_execution_confirms() -> None:
    first_zone = _zone("zone-1", "Zone 1")
    second_zone = _zone("zone-2", "Zone 2")
    person = _person(42)
    engine = _reid_engine()

    _open_reid_service(engine, first_zone, person)
    first_zone.state = ZoneState.PENDING_EXIT
    assert engine.process_zones([first_zone]) == []
    first_zone.state = ZoneState.EMPTY
    decisions = engine.process_zones([first_zone])

    assert len(decisions) == 1
    assert decisions[0].action is DispatchAction.TASK_CANCEL
    assert decisions[0].person_global_id == 42
    assert engine.get_person_service_state(42) is PersonServiceState.REQUESTED
    assert engine.get_service_state(first_zone.id) is ZoneServiceState.CANCEL_REQUESTED

    assert engine.on_service_cancelled(first_zone.id)
    assert engine.get_person_service_state(42) is None

    decision = _open_reid_service(engine, second_zone, person)
    assert decision.action is DispatchAction.TASK_ASSIGN
    assert decision.person_global_id == 42


# ─────────────────────────────────────────────────────────────────────────────
def test_failed_service_releases_person_but_not_same_zone_occupancy() -> None:
    zone = _zone("zone-1", "Zone 1")
    person = _person(42)
    engine = _reid_engine()

    _open_reid_service(engine, zone, person)
    assert engine.on_service_failed(zone.id)

    assert engine.get_person_service_state(42) is None
    assert engine.process_zones(
        [zone],
        detections=[person],
        zone_names=[zone.name],
    ) == []


# ─────────────────────────────────────────────────────────────────────────────
def test_invalid_local_request_rolls_back_person_request() -> None:
    zone = _zone("zone-1", "Zone 1")
    person = _person(42)
    engine = _reid_engine()

    _open_reid_service(engine, zone, person)
    assert engine.on_service_request_failed(zone.id)

    assert engine.get_person_service_state(42) is None


# ─────────────────────────────────────────────────────────────────────────────
def test_person_change_cancels_active_task_then_assigns_replacement() -> None:
    zone = _zone("zone-1", "Zone 1")
    first_person = _person(10)
    replacement = _person(15, track_id=15)
    engine = _reid_engine()

    _open_reid_service(engine, zone, first_person)
    cancel_decisions = engine.process_zones(
        [zone],
        detections=[replacement],
        zone_names=[zone.name],
    )

    assert len(cancel_decisions) == 1
    assert cancel_decisions[0].action is DispatchAction.TASK_CANCEL
    assert cancel_decisions[0].person_global_id == 10
    assert engine.is_awaiting_reassignment(zone.id)
    assert engine.get_person_service_state(10) is PersonServiceState.REQUESTED

    assert engine.on_service_cancelled(zone.id)
    assign_decisions = engine.process_zones(
        [zone],
        detections=[replacement],
        zone_names=[zone.name],
    )

    assert len(assign_decisions) == 1
    assert assign_decisions[0].action is DispatchAction.TASK_ASSIGN
    assert assign_decisions[0].person_global_id == 15
    assert not engine.is_awaiting_reassignment(zone.id)
    assert engine.get_person_service_state(10) is None
    assert engine.get_person_service_state(15) is PersonServiceState.REQUESTED


# ─────────────────────────────────────────────────────────────────────────────
def test_person_change_after_completion_assigns_replacement_without_cancel() -> None:
    zone = _zone("zone-1", "Zone 1")
    first_person = _person(10)
    replacement = _person(15, track_id=15)
    engine = _reid_engine()

    _open_reid_service(engine, zone, first_person)
    assert engine.on_service_completed(zone.id)

    decisions = engine.process_zones(
        [zone],
        detections=[replacement],
        zone_names=[zone.name],
    )

    assert len(decisions) == 1
    assert decisions[0].action is DispatchAction.TASK_ASSIGN
    assert decisions[0].person_global_id == 15
    assert engine.has_person_been_served(10)
    assert engine.get_person_service_state(15) is PersonServiceState.REQUESTED


# ─────────────────────────────────────────────────────────────────────────────
def test_unserved_replacement_can_take_over_from_blocked_observed_person() -> None:
    served_zone = _zone("zone-1", "Zone 1")
    next_zone = _zone("zone-2", "Zone 2")
    served_person = _person(10)
    replacement = _person(15, track_id=15)
    engine = _reid_engine()

    _open_reid_service(engine, served_zone, served_person)
    assert engine.on_service_completed(served_zone.id)

    engine.process_zones([next_zone])
    next_zone.state = ZoneState.OCCUPIED
    assert engine.process_zones(
        [next_zone],
        detections=[served_person],
        zone_names=[next_zone.name],
    ) == []

    decisions = engine.process_zones(
        [next_zone],
        detections=[replacement],
        zone_names=[next_zone.name],
    )

    assert len(decisions) == 1
    assert decisions[0].action is DispatchAction.TASK_ASSIGN
    assert decisions[0].person_global_id == 15
