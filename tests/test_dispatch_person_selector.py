from __future__ import annotations

import numpy as np

from src.detection import Detection
from src.dispatch_decision import select_zone_person
from src.zones_management import Zone


# ─────────────────────────────────────────────────────────────────────────────
def _zone(name: str = "Zone 1") -> Zone:
    """Tạo zone tối giản phục vụ kiểm thử chọn người."""
    return Zone(
        camera_id="camera-1",
        camera_name="Camera 1",
        id="zone-1",
        name=name,
        pts=np.empty((0, 2), dtype=np.int32),
        goal_pose={"x": 1.0, "y": 2.0, "theta": 0.0},
    )


# ─────────────────────────────────────────────────────────────────────────────
def _detection(
    *,
    global_id: int | None,
    similarity: float | None,
    confidence: float,
) -> Detection:
    """Tạo detection với dữ liệu ReID cần cho selector."""
    return Detection(
        bbox=(0.0, 0.0, 10.0, 20.0),
        confidence=confidence,
        global_id=global_id,
        similarity=similarity,
    )


# ─────────────────────────────────────────────────────────────────────────────
def test_selects_identified_person_with_highest_similarity() -> None:
    zone = _zone()
    lower_similarity = _detection(
        global_id=10,
        similarity=0.82,
        confidence=0.95,
    )
    higher_similarity = _detection(
        global_id=20,
        similarity=0.91,
        confidence=0.80,
    )

    selected = select_zone_person(
        zone,
        [lower_similarity, higher_similarity],
        [zone.name, zone.name],
    )

    assert selected is higher_similarity


# ─────────────────────────────────────────────────────────────────────────────
def test_ignores_people_outside_zone_and_without_global_id() -> None:
    zone = _zone()
    outside_zone = _detection(
        global_id=10,
        similarity=0.99,
        confidence=0.99,
    )
    unidentified = _detection(
        global_id=None,
        similarity=0.95,
        confidence=0.95,
    )

    selected = select_zone_person(
        zone,
        [outside_zone, unidentified],
        ["Zone 2", zone.name],
    )

    assert selected is None


# ─────────────────────────────────────────────────────────────────────────────
def test_uses_confidence_to_break_similarity_tie() -> None:
    zone = _zone()
    lower_confidence = _detection(
        global_id=10,
        similarity=0.90,
        confidence=0.80,
    )
    higher_confidence = _detection(
        global_id=20,
        similarity=0.90,
        confidence=0.95,
    )

    selected = select_zone_person(
        zone,
        [lower_confidence, higher_confidence],
        [zone.name, zone.name],
    )

    assert selected is higher_confidence


# ─────────────────────────────────────────────────────────────────────────────
def test_similarity_none_has_lowest_priority() -> None:
    zone = _zone()
    without_similarity = _detection(
        global_id=10,
        similarity=None,
        confidence=0.99,
    )
    with_similarity = _detection(
        global_id=20,
        similarity=0.10,
        confidence=0.50,
    )

    selected = select_zone_person(
        zone,
        [without_similarity, with_similarity],
        [zone.name, zone.name],
    )

    assert selected is with_similarity


# ─────────────────────────────────────────────────────────────────────────────
def test_rejects_mismatched_detection_and_zone_name_lengths() -> None:
    zone = _zone()
    person = _detection(
        global_id=10,
        similarity=0.90,
        confidence=0.95,
    )

    try:
        select_zone_person(zone, [person], [])
    except ValueError as exc:
        assert "cùng số phần tử" in str(exc)
    else:
        raise AssertionError("Selector phải từ chối hai sequence lệch độ dài")
