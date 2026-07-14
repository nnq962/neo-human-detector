from src.detection import Detection
from src.dispatch_decision import (
    DispatchAction,
    ReIdDecisionPolicy,
    ZoneOnlyDecisionPolicy,
    ZoneServiceState,
)
from src.zones_management import ZoneState


# ─────────────────────────────────────────────────────────────────────────────
def _person(
    *,
    global_id: int | None = 10,
    similarity: float | None = 0.9,
) -> Detection:
    """Tạo detection tối giản để kiểm thử policy ReID."""
    return Detection(
        bbox=(0.0, 0.0, 10.0, 20.0),
        confidence=0.95,
        global_id=global_id,
        similarity=similarity,
    )


# ─────────────────────────────────────────────────────────────────────────────
def test_zone_only_policy_keeps_current_assign_rule() -> None:
    policy = ZoneOnlyDecisionPolicy()

    action = policy.decide(
        previous_state=ZoneState.PENDING_ENTER,
        current_state=ZoneState.OCCUPIED,
        service_state=ZoneServiceState.NOT_REQUESTED,
    )

    assert action is DispatchAction.TASK_ASSIGN


# ─────────────────────────────────────────────────────────────────────────────
def test_reid_policy_waits_when_selected_person_has_no_global_id() -> None:
    policy = ReIdDecisionPolicy()

    action = policy.decide(
        previous_state=ZoneState.PENDING_ENTER,
        current_state=ZoneState.OCCUPIED,
        service_state=ZoneServiceState.NOT_REQUESTED,
        selected_person=_person(global_id=None),
        person_service_blocked=False,
        awaiting_identity=False,
        awaiting_reassignment=False,
        person_changed=False,
        active_person_global_id=None,
    )

    assert action is None


# ─────────────────────────────────────────────────────────────────────────────
def test_reid_policy_assigns_identified_unserved_person() -> None:
    policy = ReIdDecisionPolicy()

    action = policy.decide(
        previous_state=ZoneState.PENDING_ENTER,
        current_state=ZoneState.OCCUPIED,
        service_state=ZoneServiceState.NOT_REQUESTED,
        selected_person=_person(),
        person_service_blocked=False,
        awaiting_identity=False,
        awaiting_reassignment=False,
        person_changed=False,
        active_person_global_id=None,
    )

    assert action is DispatchAction.TASK_ASSIGN


# ─────────────────────────────────────────────────────────────────────────────
def test_reid_policy_blocks_person_with_existing_service() -> None:
    policy = ReIdDecisionPolicy()

    action = policy.decide(
        previous_state=ZoneState.PENDING_ENTER,
        current_state=ZoneState.OCCUPIED,
        service_state=ZoneServiceState.NOT_REQUESTED,
        selected_person=_person(),
        person_service_blocked=True,
        awaiting_identity=False,
        awaiting_reassignment=False,
        person_changed=False,
        active_person_global_id=None,
    )

    assert action is None


# ─────────────────────────────────────────────────────────────────────────────
def test_reid_policy_assigns_when_identity_appears_while_waiting() -> None:
    policy = ReIdDecisionPolicy()

    action = policy.decide(
        previous_state=ZoneState.OCCUPIED,
        current_state=ZoneState.OCCUPIED,
        service_state=ZoneServiceState.NOT_REQUESTED,
        selected_person=_person(),
        person_service_blocked=False,
        awaiting_identity=True,
        awaiting_reassignment=False,
        person_changed=False,
        active_person_global_id=None,
    )

    assert action is DispatchAction.TASK_ASSIGN


# ─────────────────────────────────────────────────────────────────────────────
def test_cancel_rule_is_shared_by_both_policy_modes() -> None:
    zone_only_action = ZoneOnlyDecisionPolicy().decide(
        previous_state=ZoneState.PENDING_EXIT,
        current_state=ZoneState.EMPTY,
        service_state=ZoneServiceState.REQUESTED,
    )
    reid_action = ReIdDecisionPolicy().decide(
        previous_state=ZoneState.PENDING_EXIT,
        current_state=ZoneState.EMPTY,
        service_state=ZoneServiceState.REQUESTED,
        selected_person=None,
        person_service_blocked=False,
        awaiting_identity=False,
        awaiting_reassignment=False,
        person_changed=False,
        active_person_global_id=None,
    )

    assert zone_only_action is DispatchAction.TASK_CANCEL
    assert reid_action is DispatchAction.TASK_CANCEL


# ─────────────────────────────────────────────────────────────────────────────
def test_reid_policy_cancels_active_task_when_person_changes() -> None:
    action = ReIdDecisionPolicy().decide(
        previous_state=ZoneState.OCCUPIED,
        current_state=ZoneState.OCCUPIED,
        service_state=ZoneServiceState.REQUESTED,
        selected_person=_person(global_id=15),
        person_service_blocked=False,
        awaiting_identity=False,
        awaiting_reassignment=False,
        person_changed=True,
        active_person_global_id=10,
    )

    assert action is DispatchAction.TASK_CANCEL


# ─────────────────────────────────────────────────────────────────────────────
def test_reid_policy_assigns_replacement_after_cancel() -> None:
    action = ReIdDecisionPolicy().decide(
        previous_state=ZoneState.OCCUPIED,
        current_state=ZoneState.OCCUPIED,
        service_state=ZoneServiceState.NOT_REQUESTED,
        selected_person=_person(global_id=15),
        person_service_blocked=False,
        awaiting_identity=False,
        awaiting_reassignment=True,
        person_changed=False,
        active_person_global_id=None,
    )

    assert action is DispatchAction.TASK_ASSIGN
