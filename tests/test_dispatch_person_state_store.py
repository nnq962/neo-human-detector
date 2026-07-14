from src.dispatch_decision import PersonServiceState, PersonServiceStateStore


# ─────────────────────────────────────────────────────────────────────────────
def test_requested_and_served_person_remains_blocked() -> None:
    store = PersonServiceStateStore()

    assert store.mark_requested(42, "zone-1")
    assert store.is_blocked(42)
    assert not store.mark_requested(42, "zone-2")
    assert store.mark_served(42, "zone-1")
    assert store.get_state(42) is PersonServiceState.SERVED
    assert not store.release_request(42, "zone-1")
    assert store.is_blocked(42)


# ─────────────────────────────────────────────────────────────────────────────
def test_release_only_removes_matching_open_request() -> None:
    store = PersonServiceStateStore()

    assert store.mark_requested(42, "zone-1")
    assert not store.release_request(42, "zone-2")
    assert store.is_blocked(42)
    assert store.release_request(42, "zone-1")
    assert not store.is_blocked(42)
