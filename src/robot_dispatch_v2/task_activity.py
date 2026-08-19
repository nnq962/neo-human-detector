"""Read-model thread-safe cho trạng thái và lịch sử robot task."""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

ACTIVE_TASK_STATUSES = {
    "WAITING_ROBOT",
    "ASSIGNING",
    "ASSIGNED",
    "IN_PROGRESS",
    "CANCELING",
}
TERMINAL_TASK_STATUSES = {"COMPLETED", "FAILED", "CANCELED"}


# ─────────────────────────────────────────────────────────────────────────────
class TaskPriority(str, Enum):
    """Mức ưu tiên dùng chung cho task từ mọi nguồn."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class TaskActivity:
    """Snapshot công khai của một task trong lifecycle runtime."""

    uid: str
    task_id: Optional[int]
    robot_id: Optional[int]
    camera_id: str
    camera_name: str
    zone_id: Optional[str]
    zone_name: Optional[str]
    origin: str
    priority: str
    target_pixel: Optional[dict[str, int]]
    goal_pose: dict[str, float]
    person_global_id: Optional[int]
    person_similarity: Optional[float]
    person_track_id: Optional[int]
    status: str
    retry_count: int
    assigned_at: str
    updated_at: str
    completed_at: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
class TaskActivityStore:
    """Lưu task active và lịch sử terminal để API/WebSocket đọc an toàn."""

    def __init__(self, *, max_history: int = 500) -> None:
        """Khởi tạo kho task với số bản ghi terminal tối đa cần giữ."""
        self._lock = threading.RLock()
        self._max_history = max(1, max_history)
        self._tasks: dict[str, TaskActivity] = {}
        self._active_uid_by_zone: dict[str, str] = {}
        self._sequence = 0
        self._session_id = uuid.uuid4().hex

    # ─────────────────────────────────────────────────────────────────────────
    def reset(self) -> None:
        """Bắt đầu lịch sử mới cho một phiên runtime mới."""
        with self._lock:
            self._tasks.clear()
            self._active_uid_by_zone.clear()
            self._session_id = uuid.uuid4().hex
            self._sequence += 1

    # ─────────────────────────────────────────────────────────────────────────
    def create_task(
        self,
        *,
        camera_id: str,
        camera_name: str,
        origin: str,
        priority: TaskPriority,
        target_pixel: Optional[tuple[float, float]],
        goal_pose: dict[str, float],
        zone_id: Optional[str] = None,
        zone_name: Optional[str] = None,
        person_global_id: Optional[int] = None,
        person_similarity: Optional[float] = None,
        person_track_id: Optional[int] = None,
    ) -> str:
        """Tạo task runtime mới cho nguồn zone hoặc thao tác thủ công."""
        now = _utc_now()
        uid = f"{self._session_id}:{uuid.uuid4().hex}"
        task = TaskActivity(
            uid=uid,
            task_id=None,
            robot_id=None,
            camera_id=camera_id,
            camera_name=camera_name,
            zone_id=zone_id,
            zone_name=zone_name,
            origin=origin,
            priority=priority.value,
            target_pixel=(
                {"x": round(target_pixel[0]), "y": round(target_pixel[1])}
                if target_pixel is not None
                else None
            ),
            goal_pose=dict(goal_pose),
            person_global_id=person_global_id,
            person_similarity=person_similarity,
            person_track_id=person_track_id,
            status="WAITING_ROBOT",
            retry_count=0,
            assigned_at=now,
            updated_at=now,
        )
        with self._lock:
            if zone_id is not None and zone_id in self._active_uid_by_zone:
                raise ValueError(f"Zone {zone_id} đang có task active")
            self._tasks[uid] = task
            if zone_id is not None:
                self._active_uid_by_zone[zone_id] = uid
            self._changed_unlocked()
        return uid

    # ─────────────────────────────────────────────────────────────────────────
    def get(self, uid: str) -> Optional[TaskActivity]:
        """Lấy snapshot task theo UID."""
        with self._lock:
            return self._tasks.get(uid)

    # ─────────────────────────────────────────────────────────────────────────
    def get_active_uid_by_zone(self, zone_id: str) -> Optional[str]:
        """Lấy UID task active hiện tại của zone."""
        with self._lock:
            return self._active_uid_by_zone.get(zone_id)

    # ─────────────────────────────────────────────────────────────────────────
    def mark_assigning(self, uid: str, robot_id: int, task_id: int) -> None:
        """Đánh dấu task đang được gửi tới robot và gắn định danh nhị phân."""
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
            self._changed_unlocked()

    # ─────────────────────────────────────────────────────────────────────────
    def mark_assigned(self, uid: str) -> None:
        """Đánh dấu robot đã nhận task thành công."""
        self._update_by_uid(uid, status="ASSIGNED", allowed={"ASSIGNING"})

    # ─────────────────────────────────────────────────────────────────────────
    def mark_in_progress(self, uid: str) -> None:
        """Đánh dấu robot đang thực hiện task."""
        self._update_by_uid(
            uid,
            status="IN_PROGRESS",
            allowed={"ASSIGNING", "ASSIGNED", "IN_PROGRESS"},
        )

    # ─────────────────────────────────────────────────────────────────────────
    def mark_completed(self, uid: str) -> None:
        """Đánh dấu task đã hoàn thành."""
        self._mark_terminal_by_uid(uid, "COMPLETED")

    # ─────────────────────────────────────────────────────────────────────────
    def mark_failed(self, uid: str) -> None:
        """Đánh dấu task thực thi thất bại."""
        self._mark_terminal_by_uid(uid, "FAILED")

    # ─────────────────────────────────────────────────────────────────────────
    def mark_cancel_requested(self, uid: str) -> None:
        """Đánh dấu task đang trong quá trình hủy."""
        self._update_by_uid(uid, status="CANCELING")

    # ─────────────────────────────────────────────────────────────────────────
    def mark_canceled(self, uid: str) -> None:
        """Đánh dấu task đã được hủy thành công."""
        self._mark_terminal_by_uid(uid, "CANCELED")

    # ─────────────────────────────────────────────────────────────────────────
    def change_priority(self, uid: str, priority: TaskPriority) -> bool:
        """Đổi priority khi task vẫn đang chờ robot."""
        with self._lock:
            task = self._tasks.get(uid)
            if task is None or task.status != "WAITING_ROBOT":
                return False
            self._tasks[uid] = replace(
                task,
                priority=priority.value,
                updated_at=_utc_now(),
            )
            self._changed_unlocked()
            return True

    # ─────────────────────────────────────────────────────────────────────────
    def increment_retry(self, uid: str) -> None:
        """Tăng số lần gửi lại của một task chưa kết thúc."""
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

    # ─────────────────────────────────────────────────────────────────────────
    def snapshot(self) -> dict:
        """Tạo snapshot bất biến cho REST API và WebSocket đọc."""
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

    # ─────────────────────────────────────────────────────────────────────────
    def _update_by_uid(
        self,
        uid: str,
        *,
        status: str,
        allowed: Optional[set[str]] = None,
    ) -> None:
        """Cập nhật trạng thái task theo UID nếu lifecycle cho phép."""
        with self._lock:
            task = self._tasks.get(uid)
            if task is None or task.status in TERMINAL_TASK_STATUSES:
                return
            if allowed is not None and task.status not in allowed:
                return
            self._tasks[uid] = replace(task, status=status, updated_at=_utc_now())
            self._changed_unlocked()

    # ─────────────────────────────────────────────────────────────────────────
    def _mark_terminal_by_uid(self, uid: str, status: str) -> None:
        """Kết thúc task theo UID và dọn index zone active."""
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
            if (
                terminal.zone_id is not None
                and self._active_uid_by_zone.get(terminal.zone_id) == uid
            ):
                self._active_uid_by_zone.pop(terminal.zone_id, None)
            self._prune_unlocked()
            self._changed_unlocked()

    # ─────────────────────────────────────────────────────────────────────────
    def _prune_unlocked(self) -> None:
        """Loại lịch sử terminal cũ vượt quá giới hạn cấu hình."""
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

    # ─────────────────────────────────────────────────────────────────────────
    def _changed_unlocked(self) -> None:
        """Tăng sequence sau mỗi thay đổi read-model."""
        self._sequence += 1


# ─────────────────────────────────────────────────────────────────────────────
def _utc_now() -> str:
    """Trả thời điểm UTC hiện tại theo định dạng ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


runtime_task_activity_store = TaskActivityStore()
