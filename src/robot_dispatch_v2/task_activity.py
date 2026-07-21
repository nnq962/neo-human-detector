"""Read-model thread-safe cho trạng thái và lịch sử robot task."""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Optional

from src.dispatch_decision import DispatchDecision


ACTIVE_TASK_STATUSES = {
    "WAITING_ROBOT",
    "ASSIGNING",
    "ASSIGNED",
    "IN_PROGRESS",
    "CANCELING",
}
TERMINAL_TASK_STATUSES = {"COMPLETED", "FAILED", "CANCELED"}


@dataclass(frozen=True)
class TaskActivity:
    uid: str
    task_id: Optional[int]
    robot_id: Optional[int]
    camera_id: str
    camera_name: str
    zone_id: str
    zone_name: str
    goal_pose: dict[str, float]
    person_global_id: Optional[int]
    person_similarity: Optional[float]
    person_track_id: Optional[int]
    status: str
    retry_count: int
    assigned_at: str
    updated_at: str
    completed_at: Optional[str] = None


class TaskActivityStore:
    """Lưu task active và lịch sử terminal để API/WebSocket đọc an toàn."""

    def __init__(self, *, max_history: int = 500) -> None:
        self._lock = threading.RLock()
        self._max_history = max(1, max_history)
        self._tasks: dict[str, TaskActivity] = {}
        self._pending_by_zone: dict[str, str] = {}
        self._by_robot_task: dict[tuple[int, int], str] = {}
        self._sequence = 0
        self._session_id = uuid.uuid4().hex

    def reset(self) -> None:
        """Bắt đầu lịch sử mới cho một phiên runtime mới."""
        with self._lock:
            self._tasks.clear()
            self._pending_by_zone.clear()
            self._by_robot_task.clear()
            self._session_id = uuid.uuid4().hex
            self._sequence += 1

    def create_assignment(
        self,
        decision: DispatchDecision,
        *,
        x: float,
        y: float,
        theta: float,
    ) -> str:
        now = _utc_now()
        uid = f"{self._session_id}:{uuid.uuid4().hex}"
        task = TaskActivity(
            uid=uid,
            task_id=None,
            robot_id=None,
            camera_id=decision.zone.camera_id,
            camera_name=decision.zone.camera_name,
            zone_id=decision.zone_id,
            zone_name=decision.zone.name,
            goal_pose={"x": x, "y": y, "theta": theta},
            person_global_id=decision.person_global_id,
            person_similarity=decision.person_similarity,
            person_track_id=decision.person_track_id,
            status="WAITING_ROBOT",
            retry_count=0,
            assigned_at=now,
            updated_at=now,
        )
        with self._lock:
            self._tasks[uid] = task
            self._pending_by_zone[decision.zone_id] = uid
            self._changed_unlocked()
        return uid

    def mark_assigning(self, uid: str, robot_id: int, task_id: int) -> None:
        with self._lock:
            task = self._tasks.get(uid)
            if task is None or task.status not in {"WAITING_ROBOT", "ASSIGNING"}:
                return
            self._tasks[uid] = replace(
                task,
                robot_id=robot_id,
                task_id=task_id,
                status="ASSIGNING",
                updated_at=_utc_now(),
            )
            self._by_robot_task[(robot_id, task_id)] = uid
            self._changed_unlocked()

    def mark_assigned(self, uid: str) -> None:
        with self._lock:
            task = self._tasks.get(uid)
            if task is None:
                return
            if task.status in {"WAITING_ROBOT", "ASSIGNING"}:
                self._tasks[uid] = replace(
                    task,
                    status="ASSIGNED",
                    updated_at=_utc_now(),
                )
                self._changed_unlocked()
            if self._pending_by_zone.get(task.zone_id) == uid:
                self._pending_by_zone.pop(task.zone_id, None)

    def mark_in_progress(self, robot_id: int, task_id: int) -> None:
        with self._lock:
            uid = self._by_robot_task.get((robot_id, task_id))
            task = self._tasks.get(uid) if uid is not None else None
            if task is None or task.status not in {
                "WAITING_ROBOT",
                "ASSIGNING",
                "ASSIGNED",
                "IN_PROGRESS",
            }:
                return
            self._tasks[task.uid] = replace(
                task,
                status="IN_PROGRESS",
                updated_at=_utc_now(),
            )
            self._changed_unlocked()

    def mark_completed(self, robot_id: int, task_id: int) -> None:
        self._mark_terminal_by_robot_task(robot_id, task_id, "COMPLETED")

    def mark_failed(self, robot_id: int, task_id: int) -> None:
        self._mark_terminal_by_robot_task(robot_id, task_id, "FAILED")

    def mark_cancel_requested(
        self,
        zone_id: str,
        *,
        robot_id: Optional[int] = None,
        task_id: Optional[int] = None,
    ) -> None:
        with self._lock:
            uid = (
                self._by_robot_task.get((robot_id, task_id))
                if robot_id is not None and task_id is not None
                else self._pending_by_zone.get(zone_id)
            )
        if uid is not None:
            self._update_by_uid(uid, status="CANCELING")

    def mark_canceled(
        self,
        zone_id: str,
        *,
        robot_id: Optional[int] = None,
        task_id: Optional[int] = None,
    ) -> None:
        with self._lock:
            uid = (
                self._by_robot_task.get((robot_id, task_id))
                if robot_id is not None and task_id is not None
                else self._pending_by_zone.get(zone_id)
            )
        if uid is not None:
            self._mark_terminal_by_uid(uid, "CANCELED")

    def increment_retry(self, uid: str) -> None:
        with self._lock:
            task = self._tasks.get(uid)
            if task is None or task.status in TERMINAL_TASK_STATUSES:
                return
            self._tasks[uid] = replace(
                task,
                retry_count=task.retry_count + 1,
                updated_at=_utc_now(),
            )
            self._changed_unlocked()

    def increment_cancel_retry(self, robot_id: int, task_id: int) -> None:
        with self._lock:
            uid = self._by_robot_task.get((robot_id, task_id))
        if uid is not None:
            self.increment_retry(uid)

    def snapshot(self) -> dict:
        with self._lock:
            tasks = sorted(
                self._tasks.values(),
                key=lambda task: task.assigned_at,
                reverse=True,
            )
            return {
                "sequence": self._sequence,
                "total": len(tasks),
                "active": sum(task.status in ACTIVE_TASK_STATUSES for task in tasks),
                "completed": sum(task.status == "COMPLETED" for task in tasks),
                "canceled": sum(task.status == "CANCELED" for task in tasks),
                "failed": sum(task.status == "FAILED" for task in tasks),
                "tasks": [asdict(task) for task in tasks],
            }

    def _update_by_uid(self, uid: str, *, status: str) -> None:
        with self._lock:
            task = self._tasks.get(uid)
            if task is None or task.status in TERMINAL_TASK_STATUSES:
                return
            self._tasks[uid] = replace(
                task,
                status=status,
                updated_at=_utc_now(),
            )
            self._changed_unlocked()

    def _mark_terminal_by_robot_task(
        self,
        robot_id: int,
        task_id: int,
        status: str,
    ) -> None:
        with self._lock:
            uid = self._by_robot_task.get((robot_id, task_id))
        if uid is not None:
            self._mark_terminal_by_uid(uid, status)

    def _mark_terminal_by_uid(self, uid: str, status: str) -> None:
        now = _utc_now()
        with self._lock:
            task = self._tasks.get(uid)
            if task is None or task.status in TERMINAL_TASK_STATUSES:
                return
            terminal = replace(
                task,
                status=status,
                updated_at=now,
                completed_at=now,
            )
            self._tasks[uid] = terminal
            if terminal.robot_id is not None and terminal.task_id is not None:
                self._by_robot_task.pop(
                    (terminal.robot_id, terminal.task_id),
                    None,
                )
            if self._pending_by_zone.get(terminal.zone_id) == uid:
                self._pending_by_zone.pop(terminal.zone_id, None)
            self._prune_unlocked()
            self._changed_unlocked()

    def _prune_unlocked(self) -> None:
        terminal_tasks = sorted(
            (
                task
                for task in self._tasks.values()
                if task.status in TERMINAL_TASK_STATUSES
            ),
            key=lambda task: task.updated_at,
            reverse=True,
        )
        for task in terminal_tasks[self._max_history :]:
            self._tasks.pop(task.uid, None)

    def _changed_unlocked(self) -> None:
        self._sequence += 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


runtime_task_activity_store = TaskActivityStore()
