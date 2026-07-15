from api.services.robot_heartbeat import RobotHeartbeatService
from src.robot_dispatch_v2.datatypes import Heartbeat, MessageType, RobotStateCode
from src.robot_dispatch_v2.robot_state import RobotStateStore


# ─────────────────────────────────────────────────────────────────────────────
class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ─────────────────────────────────────────────────────────────────────────────
class FakeTransport:
    def __init__(self) -> None:
        self.handlers = {}

    def add_handler(self, message_type, handler) -> None:
        self.handlers.setdefault(int(message_type), []).append(handler)

    def remove_handler(self, message_type, handler) -> None:
        self.handlers.get(int(message_type), []).remove(handler)

    def emit(self, heartbeat: Heartbeat) -> None:
        for handler in self.handlers.get(int(MessageType.HEARTBEAT), ()):
            handler(heartbeat)


# ─────────────────────────────────────────────────────────────────────────────
def test_service_tracks_heartbeat_and_marks_robot_offline_when_stale() -> None:
    clock = FakeClock()
    store = RobotStateStore(clock=clock)
    service = RobotHeartbeatService(store, clock=clock)
    transport = FakeTransport()
    service.register_uart_handler(transport)

    transport.emit(
        Heartbeat(
            robot_id=2,
            timestamp=123,
            x=1.25,
            y=2.5,
            theta=0.75,
            state_code=RobotStateCode.IDLE,
        )
    )

    snapshot = service.snapshot()
    assert snapshot["total"] == 1
    assert snapshot["online"] == 1
    assert snapshot["robots"][0] == {
        "robot_id": 2,
        "state": "IDLE",
        "state_code": RobotStateCode.IDLE,
        "online": True,
        "heartbeat_timestamp": 123,
        "heartbeat_age_seconds": 0.0,
        "x": 1.25,
        "y": 2.5,
        "theta": 0.75,
    }

    clock.advance(5.01)

    stale_snapshot = service.snapshot()
    assert stale_snapshot["online"] == 0
    assert stale_snapshot["robots"][0]["online"] is False


# ─────────────────────────────────────────────────────────────────────────────
def test_close_stops_service_from_receiving_more_heartbeats() -> None:
    clock = FakeClock()
    service = RobotHeartbeatService(
        RobotStateStore(clock=clock),
        clock=clock,
    )
    transport = FakeTransport()
    service.register_uart_handler(transport)
    service.close()

    transport.emit(
        Heartbeat(
            robot_id=1,
            timestamp=1,
            x=0.0,
            y=0.0,
            theta=0.0,
            state_code=RobotStateCode.IDLE,
        )
    )

    assert service.snapshot()["robots"] == []
