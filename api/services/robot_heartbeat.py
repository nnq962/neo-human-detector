"""Theo dõi trạng thái robot từ Heartbeat trong suốt vòng đời FastAPI."""

from __future__ import annotations

import threading
import time
from typing import Callable, Protocol

from src.robot_dispatch_v2.datatypes import Heartbeat, MessageType, RobotStateCode
from src.robot_dispatch_v2.robot_state import RobotStateStore


# ─────────────────────────────────────────────────────────────────────────────
class HeartbeatTransport(Protocol):
    """Phần giao tiếp UART cần thiết để đăng ký subscriber Heartbeat."""

    def add_handler(self, message_type: int, handler) -> None:
        """Đăng ký thêm một handler cho loại message."""

    def remove_handler(self, message_type: int, handler) -> None:
        """Gỡ handler đã đăng ký trước đó."""


# ─────────────────────────────────────────────────────────────────────────────
class RobotHeartbeatService:
    """
    Giữ RobotStateStore dùng chung cho API và RobotDispatcherV2.

    Service được đăng ký trực tiếp với UART manager ở startup nên vẫn tiếp tục
    nhận Heartbeat khi vision Runtime chưa chạy hoặc đã dừng.
    """

    def __init__(
        self,
        state_store: RobotStateStore | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Khởi tạo service với store được truyền vào hoặc một store mới."""
        self.state_store = state_store or RobotStateStore()
        self._clock = clock
        self._lock = threading.RLock()
        self._transport: HeartbeatTransport | None = None

    # ─────────────────────────────────────────────────────────────────────────
    def register_uart_handler(self, transport: HeartbeatTransport) -> None:
        """Đăng ký nhận Heartbeat, không đăng ký trùng trên cùng transport."""
        with self._lock:
            if self._transport is transport:
                return

            previous_transport = self._transport
            self._transport = transport

        if previous_transport is not None:
            previous_transport.remove_handler(MessageType.HEARTBEAT, self.on_heartbeat)

        transport.add_handler(MessageType.HEARTBEAT, self.on_heartbeat)

    # ─────────────────────────────────────────────────────────────────────────
    def close(self) -> None:
        """Gỡ subscriber Heartbeat khỏi UART manager hiện tại."""
        with self._lock:
            transport = self._transport
            self._transport = None

        if transport is not None:
            transport.remove_handler(MessageType.HEARTBEAT, self.on_heartbeat)

    # ─────────────────────────────────────────────────────────────────────────
    def on_heartbeat(self, heartbeat: Heartbeat) -> None:
        """Cập nhật snapshot mới nhất khi UART nhận được Heartbeat."""
        self.state_store.update_from_heartbeat(heartbeat)

    # ─────────────────────────────────────────────────────────────────────────
    def snapshot(self) -> dict:
        """Trả danh sách robot và thống kê heartbeat ở dạng an toàn cho JSON."""
        now = self._clock()
        robots = [
            self._serialize_robot(robot, now)
            for robot in sorted(
                self.state_store.all_snapshots(),
                key=lambda item: item.robot_id,
            )
        ]
        online_count = sum(robot["online"] for robot in robots)
        latest_age = min(
            (robot["heartbeat_age_seconds"] for robot in robots),
            default=None,
        )

        return {
            "total": len(robots),
            "online": online_count,
            "latest_heartbeat_age_seconds": latest_age,
            "robots": robots,
        }

    # ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _serialize_robot(robot, now: float) -> dict:
        """Chuyển một RobotSnapshot thành payload API."""
        heartbeat_age_seconds = round(max(0.0, now - robot.updated_at), 3)
        try:
            state = RobotStateCode(robot.state_code).name
        except ValueError:
            state = "UNKNOWN"

        return {
            "robot_id": robot.robot_id,
            "state": state,
            "state_code": robot.state_code,
            "online": not robot.is_stale(now),
            "heartbeat_timestamp": robot.heartbeat_timestamp,
            "heartbeat_age_seconds": heartbeat_age_seconds,
            "x": robot.x,
            "y": robot.y,
            "theta": robot.theta,
        }


# ─────────────────────────────────────────────────────────────────────────────
robot_heartbeat_service = RobotHeartbeatService()
