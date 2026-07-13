"""
Lưu vị trí/trạng thái mới nhất của từng robot, cập nhật từ Heartbeat.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Collection, Dict, List, Optional

from src.robot_dispatch_v2.datatypes import Heartbeat, RobotStateCode

# Quá thời gian này (giây) mà không có Heartbeat mới -> coi robot mất kết nối,
# không đáng tin để chọn giao task (dù state_code cũ vẫn ghi là IDLE).
ROBOT_HEARTBEAT_STALE_SECONDS = 5.0

# Khoảng cách (mét) coi là "robot đang đứng tại điểm đó"
ROBOT_AT_POINT_DISTANCE_METERS = 0.1


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RobotSnapshot:
    """Vị trí/trạng thái mới nhất của 1 robot, chụp lại từ Heartbeat gần nhất."""

    robot_id: int
    x: float
    y: float
    theta: float
    state_code: int
    heartbeat_timestamp: int
    updated_at: float  # thời điểm monotonic nhận Heartbeat, chỉ dùng để tính độ cũ

    def is_stale(
        self,
        now: Optional[float] = None,
        stale_after: float = ROBOT_HEARTBEAT_STALE_SECONDS,
    ) -> bool:
        """True nếu quá ``stale_after`` giây không có Heartbeat mới."""
        now = time.monotonic() if now is None else now
        return (now - self.updated_at) > stale_after


# ─────────────────────────────────────────────────────────────────────────────
class RobotStateStore:
    """
    Sổ lưu snapshot vị trí/trạng thái mới nhất của từng robot.

    Nguồn duy nhất cập nhật sổ này là update_from_heartbeat(), gọi từ handler
    đăng ký qua uart_manager_v2.set_handler(MessageType.HEARTBEAT, ...). Đọc
    sổ này (get/idle_robots/nearest_idle_robot/is_robot_at) an toàn để gọi từ
    thread khác, vì mọi thao tác đều qua self._lock.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        heartbeat_stale_seconds: float = ROBOT_HEARTBEAT_STALE_SECONDS,
        at_point_distance_meters: float = ROBOT_AT_POINT_DISTANCE_METERS,
    ) -> None:
        """Khởi tạo kho snapshot robot rỗng."""
        self._lock = threading.RLock()
        self._clock = clock
        self._heartbeat_stale_seconds = heartbeat_stale_seconds
        self._at_point_distance_meters = at_point_distance_meters
        self._snapshots: Dict[int, RobotSnapshot] = {}  # {robot_id: RobotSnapshot, ...}

    # ─────────────────────────────────────────────────────────────────────
    def update_from_heartbeat(self, heartbeat: Heartbeat) -> None:
        """Cập nhật snapshot; bỏ qua Heartbeat cũ đến trễ."""
        with self._lock:
            current = self._snapshots.get(heartbeat.robot_id)
            if current is not None and heartbeat.timestamp < current.heartbeat_timestamp:
                return

            snapshot = RobotSnapshot(
                robot_id=heartbeat.robot_id,
                x=heartbeat.x,
                y=heartbeat.y,
                theta=heartbeat.theta,
                state_code=heartbeat.state_code,
                heartbeat_timestamp=heartbeat.timestamp,
                updated_at=self._clock(),
            )
            self._snapshots[heartbeat.robot_id] = snapshot

    # ─────────────────────────────────────────────────────────────────────
    def get(self, robot_id: int) -> Optional[RobotSnapshot]:
        """Trả snapshot mới nhất của 1 robot, None nếu chưa từng nhận Heartbeat."""
        with self._lock:
            return self._snapshots.get(robot_id)

    # ─────────────────────────────────────────────────────────────────────
    def all_snapshots(self) -> List[RobotSnapshot]:
        """Trả snapshot của toàn bộ robot đã từng gửi Heartbeat (kể cả đã stale)."""
        with self._lock:
            return list(self._snapshots.values())

    # ─────────────────────────────────────────────────────────────────────
    def idle_robots(self) -> List[RobotSnapshot]:
        """Trả các robot đang IDLE và Heartbeat còn mới (chưa stale)."""
        now = self._clock()
        with self._lock:
            snapshots = list(self._snapshots.values())
        return [
            snapshot
            for snapshot in snapshots
            if snapshot.state_code == RobotStateCode.IDLE
            and not snapshot.is_stale(now, self._heartbeat_stale_seconds)
        ]

    # ─────────────────────────────────────────────────────────────────────
    def nearest_idle_robot(
        self,
        x: float,
        y: float,
        excluded_robot_ids: Optional[Collection[int]] = None,
    ) -> Optional[RobotSnapshot]:
        """
        Một RobotSnapshot của robot gần tọa độ (x, y) nhất, với điều kiện:
            - Robot đang ở trạng thái IDLE.
            - Heartbeat chưa vượt ngưỡng stale đã cấu hình.
            - Robot không nằm trong excluded_robot_ids.
        """
        excluded = excluded_robot_ids or ()
        return min(
            (
                snapshot
                for snapshot in self.idle_robots()
                if snapshot.robot_id not in excluded
            ),
            key=lambda snapshot: (
                _distance(snapshot.x, snapshot.y, x, y),
                snapshot.robot_id,
            ),
            default=None,
        )

    # ─────────────────────────────────────────────────────────────────────
    def is_robot_at(self, robot_id: int, x: float, y: float) -> bool:
        """
        True nếu robot đang đứng trong ngưỡng khoảng cách đã cấu hình tới điểm (x, y).
        Trả False nếu chưa có snapshot hoặc Heartbeat đã stale.
        """
        snapshot = self.get(robot_id)
        now = self._clock()
        if snapshot is None or snapshot.is_stale(now, self._heartbeat_stale_seconds):
            return False
        return _distance(snapshot.x, snapshot.y, x, y) <= self._at_point_distance_meters


# ─────────────────────────────────────────────────────────────────────────────
def _distance(x1: float, y1: float, x2: float, y2: float) -> float:
    """Khoảng cách Euclid 2D giữa 2 điểm, đơn vị mét (khớp đơn vị x/y trong Heartbeat)."""
    return math.hypot(x1 - x2, y1 - y2)
