"""Cấp ``move_id`` và bảo vệ một lệnh MoveToPoint đang hoạt động mỗi robot."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

from src.robot_dispatch_v2.datatypes import RobotStateCode
from src.robot_dispatch_v2.robot_state import RobotStateStore


MOVE_ID_MIN = 0
MOVE_ID_MAX = 255


class RobotMoveBusyError(RuntimeError):
    """Báo robot đang bận và không thể nhận MoveToPoint mới."""


class RobotMoveUnavailableError(RuntimeError):
    """Báo chưa có Heartbeat mới để gửi lệnh an toàn."""


@dataclass(frozen=True)
class MoveReservation:
    """Một ``move_id`` đã được backend giữ chỗ cho robot."""

    robot_id: int
    move_id: int
    reserved_at: float
    release_after: float | None = None
    observed_busy: bool = False


class RobotMoveRegistry:
    """Registry in-memory cấp ID tuần tự và theo dõi lệnh đang chạy."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        """Khởi tạo registry rỗng với đồng hồ monotonic."""
        self._clock = clock
        self._lock = threading.RLock()
        self._active: dict[int, MoveReservation] = {}
        self._next_move_id: dict[int, int] = {}

    # ─────────────────────────────────────────────────────────────────────────
    def reserve(self, robot_id: int, state_store: RobotStateStore) -> MoveReservation:
        """Kiểm tra robot IDLE và cấp ID mới, không cho cấp lệnh song song."""
        now = self._clock()
        with self._lock:
            self._release_completed_locked(robot_id, state_store, now)
            if robot_id in self._active:
                raise RobotMoveBusyError(f"Robot {robot_id} đang thực hiện lệnh di chuyển.")

            snapshot = state_store.get(robot_id)
            if snapshot is None or snapshot.is_stale(now):
                raise RobotMoveUnavailableError(
                    f"Robot {robot_id} chưa có Heartbeat mới hoặc đã offline."
                )
            if snapshot.state_code != RobotStateCode.IDLE:
                raise RobotMoveBusyError(
                    f"Robot {robot_id} không ở trạng thái IDLE."
                )

            move_id = self._next_move_id.get(robot_id, MOVE_ID_MIN)
            self._next_move_id[robot_id] = (
                MOVE_ID_MIN + ((move_id + 1) % (MOVE_ID_MAX + 1))
            )
            reservation = MoveReservation(
                robot_id=robot_id,
                move_id=move_id,
                reserved_at=now,
            )
            self._active[robot_id] = reservation
            return reservation

    # ─────────────────────────────────────────────────────────────────────────
    def mark_accepted(self, reservation: MoveReservation) -> None:
        """Giữ ID tới khi có Heartbeat IDLE mới hơn thời điểm nhận ACK."""
        self._set_release_barrier(reservation, reservation.reserved_at)

    # ─────────────────────────────────────────────────────────────────────────
    def mark_uncertain(self, reservation: MoveReservation) -> None:
        """Giữ ID khi mất ACK vì robot có thể đã nhận và đang di chuyển."""
        self._set_release_barrier(reservation, reservation.reserved_at)

    # ─────────────────────────────────────────────────────────────────────────
    def mark_rejected(
        self,
        reservation: MoveReservation,
        *,
        robot_busy: bool,
    ) -> None:
        """Giải phóng rejection thường hoặc chờ IDLE nếu robot báo đang bận."""
        if robot_busy:
            self._set_release_barrier(
                reservation,
                reservation.reserved_at,
                observed_busy=True,
            )
            return
        with self._lock:
            active = self._active.get(reservation.robot_id)
            if active is not None and (
                active.robot_id == reservation.robot_id
                and active.move_id == reservation.move_id
                and active.reserved_at == reservation.reserved_at
            ):
                self._active.pop(reservation.robot_id, None)

    # ─────────────────────────────────────────────────────────────────────────
    def has_active_move(self, robot_id: int, state_store: RobotStateStore) -> bool:
        """Kiểm tra robot còn lệnh đang hoạt động sau khi đối chiếu Heartbeat."""
        now = self._clock()
        with self._lock:
            self._release_completed_locked(robot_id, state_store, now)
            return robot_id in self._active

    # ─────────────────────────────────────────────────────────────────────────
    def has_any_active_move(self, state_store: RobotStateStore) -> bool:
        """Kiểm tra còn bất kỳ MoveToPoint nào chưa được Heartbeat giải phóng."""
        now = self._clock()
        with self._lock:
            for robot_id in list(self._active):
                self._release_completed_locked(robot_id, state_store, now)
            return bool(self._active)

    # ─────────────────────────────────────────────────────────────────────────
    def observe_heartbeat(
        self,
        robot_id: int,
        state_store: RobotStateStore,
    ) -> None:
        """Ghi nhận từng chuyển trạng thái để không bỏ lỡ chu kỳ BUSY rồi IDLE."""
        now = self._clock()
        with self._lock:
            active = self._active.get(robot_id)
            snapshot = state_store.get(robot_id)
            if active is None or snapshot is None or snapshot.is_stale(now):
                return

            if (
                snapshot.updated_at >= active.reserved_at
                and snapshot.state_code != RobotStateCode.IDLE
                and not active.observed_busy
            ):
                self._active[robot_id] = MoveReservation(
                    robot_id=active.robot_id,
                    move_id=active.move_id,
                    reserved_at=active.reserved_at,
                    release_after=active.release_after,
                    observed_busy=True,
                )

            self._release_completed_locked(robot_id, state_store, now)

    # ─────────────────────────────────────────────────────────────────────────
    def reset(self) -> None:
        """Xóa state cấp ID, chủ yếu phục vụ kiểm thử độc lập."""
        with self._lock:
            self._active.clear()
            self._next_move_id.clear()

    # ─────────────────────────────────────────────────────────────────────────
    def _set_release_barrier(
        self,
        reservation: MoveReservation,
        release_after: float,
        *,
        observed_busy: bool = False,
    ) -> None:
        """Cập nhật mốc Heartbeat tối thiểu để giải phóng reservation."""
        with self._lock:
            active = self._active.get(reservation.robot_id)
            if active is None or (
                active.robot_id != reservation.robot_id
                or active.move_id != reservation.move_id
                or active.reserved_at != reservation.reserved_at
            ):
                return
            self._active[reservation.robot_id] = MoveReservation(
                robot_id=reservation.robot_id,
                move_id=reservation.move_id,
                reserved_at=reservation.reserved_at,
                release_after=release_after,
                observed_busy=active.observed_busy or observed_busy,
            )

    # ─────────────────────────────────────────────────────────────────────────
    def _release_completed_locked(
        self,
        robot_id: int,
        state_store: RobotStateStore,
        now: float,
    ) -> None:
        """Giải phóng khi robot online và báo IDLE sau mốc ACK/timeout."""
        active = self._active.get(robot_id)
        if active is None or active.release_after is None:
            return

        snapshot = state_store.get(robot_id)
        if (
            snapshot is None
            or snapshot.is_stale(now)
            or snapshot.updated_at <= active.release_after
        ):
            return

        if snapshot.state_code != RobotStateCode.IDLE:
            if not active.observed_busy:
                self._active[robot_id] = MoveReservation(
                    robot_id=active.robot_id,
                    move_id=active.move_id,
                    reserved_at=active.reserved_at,
                    release_after=active.release_after,
                    observed_busy=True,
                )
            return

        if active.observed_busy:
            self._active.pop(robot_id, None)


robot_move_registry = RobotMoveRegistry()
