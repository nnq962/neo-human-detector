"""Kiểm thử cấp move_id và vòng đời lệnh di chuyển thủ công."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from api.services.robot_move import RobotMoveBusyError, RobotMoveRegistry
from api.services.robot_heartbeat import RobotHeartbeatService
from src.robot_dispatch_v2.datatypes import Heartbeat, RobotStateCode
from src.robot_dispatch_v2.robot_state import RobotStateStore


class FakeClock:
    """Đồng hồ dùng chung cho registry và RobotStateStore."""

    def __init__(self) -> None:
        """Khởi tạo đồng hồ ở mốc không."""
        self.now = 0.0

    # ─────────────────────────────────────────────────────────────────────────
    def __call__(self) -> float:
        """Trả thời gian hiện tại."""
        return self.now

    # ─────────────────────────────────────────────────────────────────────────
    def advance(self, seconds: float = 1.0) -> None:
        """Tiến đồng hồ để Heartbeat sau có mốc mới hơn ACK."""
        self.now += seconds


# ─────────────────────────────────────────────────────────────────────────────
def _heartbeat(
    state_store: RobotStateStore,
    clock: FakeClock,
    state: RobotStateCode,
) -> None:
    """Ghi một Heartbeat mới cho robot #1."""
    state_store.update_from_heartbeat(
        Heartbeat(
            robot_id=1,
            timestamp=int(clock.now),
            x=0.0,
            y=0.0,
            theta=0.0,
            state_code=state,
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
def test_move_id_is_sequential_and_released_by_new_idle_heartbeat() -> None:
    """Kiểm tra ID tăng tuần tự và chỉ giải phóng sau Heartbeat IDLE mới."""
    clock = FakeClock()
    state_store = RobotStateStore(clock=clock)
    registry = RobotMoveRegistry(clock=clock)
    _heartbeat(state_store, clock, RobotStateCode.IDLE)

    first = registry.reserve(1, state_store)
    assert first.move_id == 0
    registry.mark_accepted(first)

    with pytest.raises(RobotMoveBusyError):
        registry.reserve(1, state_store)

    clock.advance()
    _heartbeat(state_store, clock, RobotStateCode.IDLE)
    with pytest.raises(RobotMoveBusyError):
        registry.reserve(1, state_store)

    clock.advance()
    _heartbeat(state_store, clock, RobotStateCode.SERVING)
    with pytest.raises(RobotMoveBusyError):
        registry.reserve(1, state_store)

    clock.advance()
    _heartbeat(state_store, clock, RobotStateCode.IDLE)
    second = registry.reserve(1, state_store)
    assert second.move_id == 1


# ─────────────────────────────────────────────────────────────────────────────
def test_timeout_keeps_robot_blocked_until_idle_heartbeat() -> None:
    """Kiểm tra mất ACK không làm backend cấp lệnh mới nguy hiểm."""
    clock = FakeClock()
    state_store = RobotStateStore(clock=clock)
    registry = RobotMoveRegistry(clock=clock)
    _heartbeat(state_store, clock, RobotStateCode.IDLE)

    reservation = registry.reserve(1, state_store)
    registry.mark_uncertain(reservation)
    with pytest.raises(RobotMoveBusyError):
        registry.reserve(1, state_store)

    clock.advance()
    _heartbeat(state_store, clock, RobotStateCode.SERVING)
    assert registry.has_active_move(1, state_store)
    clock.advance()
    _heartbeat(state_store, clock, RobotStateCode.IDLE)
    assert registry.reserve(1, state_store).move_id == 1


# ─────────────────────────────────────────────────────────────────────────────
def test_busy_heartbeat_before_ack_is_not_lost() -> None:
    """Kiểm tra Heartbeat BUSY đến trước ACK vẫn mở khóa ở IDLE kế tiếp."""
    clock = FakeClock()
    state_store = RobotStateStore(clock=clock)
    registry = RobotMoveRegistry(clock=clock)
    _heartbeat(state_store, clock, RobotStateCode.IDLE)

    reservation = registry.reserve(1, state_store)
    clock.advance()
    _heartbeat(state_store, clock, RobotStateCode.SERVING)
    registry.observe_heartbeat(1, state_store)
    clock.advance()
    registry.mark_accepted(reservation)

    clock.advance()
    _heartbeat(state_store, clock, RobotStateCode.IDLE)
    registry.observe_heartbeat(1, state_store)
    assert registry.reserve(1, state_store).move_id == 1


# ─────────────────────────────────────────────────────────────────────────────
def test_heartbeat_observer_releases_without_an_intermediate_api_poll() -> None:
    """Kiểm tra registry không bỏ lỡ cả chu kỳ BUSY rồi IDLE giữa hai request."""
    clock = FakeClock()
    state_store = RobotStateStore(clock=clock)
    registry = RobotMoveRegistry(clock=clock)
    _heartbeat(state_store, clock, RobotStateCode.IDLE)

    reservation = registry.reserve(1, state_store)
    registry.mark_accepted(reservation)
    clock.advance()
    _heartbeat(state_store, clock, RobotStateCode.SERVING)
    registry.observe_heartbeat(1, state_store)
    clock.advance()
    _heartbeat(state_store, clock, RobotStateCode.IDLE)
    registry.observe_heartbeat(1, state_store)

    assert registry.reserve(1, state_store).move_id == 1


# ─────────────────────────────────────────────────────────────────────────────
def test_heartbeat_service_forwards_each_state_to_move_registry(monkeypatch) -> None:
    """Kiểm tra heartbeat service nối đầy đủ vòng đời robot vào registry."""
    clock = FakeClock()
    state_store = RobotStateStore(clock=clock)
    registry = RobotMoveRegistry(clock=clock)
    service = RobotHeartbeatService(state_store=state_store, clock=clock)
    monkeypatch.setattr("api.services.robot_move.robot_move_registry", registry)

    service.on_heartbeat(
        Heartbeat(
            robot_id=1,
            timestamp=0,
            x=0,
            y=0,
            theta=0,
            state_code=RobotStateCode.IDLE,
        )
    )
    reservation = registry.reserve(1, state_store)
    registry.mark_accepted(reservation)

    clock.advance()
    service.on_heartbeat(
        Heartbeat(
            robot_id=1,
            timestamp=1,
            x=0,
            y=0,
            theta=0,
            state_code=RobotStateCode.SERVING,
        )
    )
    clock.advance()
    service.on_heartbeat(
        Heartbeat(
            robot_id=1,
            timestamp=2,
            x=1,
            y=2,
            theta=0,
            state_code=RobotStateCode.IDLE,
        )
    )

    assert registry.reserve(1, state_store).move_id == 1


# ─────────────────────────────────────────────────────────────────────────────
def test_concurrent_reservations_allow_only_one_active_move() -> None:
    """Kiểm tra request đồng thời không thể nhận hai move_id cho cùng robot."""
    clock = FakeClock()
    state_store = RobotStateStore(clock=clock)
    registry = RobotMoveRegistry(clock=clock)
    _heartbeat(state_store, clock, RobotStateCode.IDLE)

    def reserve_once(_: int) -> int | None:
        """Thử giữ ID và đổi lỗi busy thành ``None`` để dễ thống kê."""
        try:
            return registry.reserve(1, state_store).move_id
        except RobotMoveBusyError:
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(reserve_once, range(16)))

    assert [move_id for move_id in results if move_id is not None] == [0]


# ─────────────────────────────────────────────────────────────────────────────
def test_move_id_wraps_only_after_completed_commands() -> None:
    """Kiểm tra uint8 quay vòng sau khi từng lệnh đã hoàn thành an toàn."""
    clock = FakeClock()
    state_store = RobotStateStore(clock=clock)
    registry = RobotMoveRegistry(clock=clock)
    _heartbeat(state_store, clock, RobotStateCode.IDLE)

    allocated: list[int] = []
    for _ in range(257):
        reservation = registry.reserve(1, state_store)
        allocated.append(reservation.move_id)
        registry.mark_accepted(reservation)
        clock.advance()
        _heartbeat(state_store, clock, RobotStateCode.SERVING)
        assert registry.has_active_move(1, state_store)
        clock.advance()
        _heartbeat(state_store, clock, RobotStateCode.IDLE)

    assert allocated[:256] == list(range(256))
    assert allocated[256] == 0
