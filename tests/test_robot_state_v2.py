from src.robot_dispatch_v2.datatypes import Heartbeat, RobotStateCode
from src.robot_dispatch_v2.robot_state import RobotStateStore


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _heartbeat(
    robot_id: int,
    *,
    timestamp: int = 1,
    x: float = 0.0,
    y: float = 0.0,
    state_code: int = RobotStateCode.IDLE,
) -> Heartbeat:
    return Heartbeat(
        robot_id=robot_id,
        timestamp=timestamp,
        x=x,
        y=y,
        theta=0.0,
        state_code=state_code,
    )


def test_nearest_idle_robot_filters_state_staleness_and_exclusions() -> None:
    clock = FakeClock()
    store = RobotStateStore(clock=clock)
    store.update_from_heartbeat(_heartbeat(1, x=1.0))
    store.update_from_heartbeat(_heartbeat(2, x=2.0))
    store.update_from_heartbeat(
        _heartbeat(3, x=0.5, state_code=RobotStateCode.SERVING)
    )

    assert store.nearest_idle_robot(0.0, 0.0).robot_id == 1
    assert store.nearest_idle_robot(0.0, 0.0, {1}).robot_id == 2

    clock.advance(5.01)
    assert store.nearest_idle_robot(0.0, 0.0) is None


def test_nearest_idle_robot_uses_robot_id_to_break_distance_tie() -> None:
    store = RobotStateStore(clock=FakeClock())
    store.update_from_heartbeat(_heartbeat(2, x=-1.0))
    store.update_from_heartbeat(_heartbeat(1, x=1.0))

    assert store.nearest_idle_robot(0.0, 0.0).robot_id == 1


def test_is_robot_at_rejects_stale_snapshot_and_includes_distance_boundary() -> None:
    clock = FakeClock()
    store = RobotStateStore(clock=clock)
    store.update_from_heartbeat(_heartbeat(1, x=0.1))

    assert store.is_robot_at(1, 0.0, 0.0)

    clock.advance(5.01)
    assert not store.is_robot_at(1, 0.0, 0.0)


def test_older_heartbeat_does_not_overwrite_newer_snapshot() -> None:
    clock = FakeClock()
    store = RobotStateStore(clock=clock)
    store.update_from_heartbeat(_heartbeat(1, timestamp=20, x=2.0))
    clock.advance(1.0)
    store.update_from_heartbeat(_heartbeat(1, timestamp=19, x=9.0))

    snapshot = store.get(1)
    assert snapshot is not None
    assert snapshot.x == 2.0
    assert snapshot.heartbeat_timestamp == 20
    assert snapshot.updated_at == 0.0


def test_equal_timestamp_heartbeat_is_still_accepted() -> None:
    clock = FakeClock()
    store = RobotStateStore(clock=clock)
    store.update_from_heartbeat(_heartbeat(1, timestamp=20, x=1.0))
    clock.advance(1.0)
    store.update_from_heartbeat(_heartbeat(1, timestamp=20, x=2.0))

    snapshot = store.get(1)
    assert snapshot is not None
    assert snapshot.x == 2.0
    assert snapshot.updated_at == 1.0
