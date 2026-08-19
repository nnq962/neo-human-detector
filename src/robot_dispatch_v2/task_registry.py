"""Cấp task ID và lưu quan hệ giữa robot task với task runtime."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


TASK_ID_MIN = 0
TASK_ID_MAX = 255


# ─────────────────────────────────────────────────────────────────────────────
class TaskRegistryFull(RuntimeError):
    """Robot đã dùng hết toàn bộ task ID có thể biểu diễn bằng uint8."""

    def __init__(self, robot_id: int) -> None:
        """Khởi tạo lỗi cho robot không còn task ID khả dụng."""
        self.robot_id = robot_id
        super().__init__(f"Robot {robot_id} đã dùng hết task_id từ 0 đến 255")


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class AssignedTask:
    """Một task runtime đã được giữ chỗ trên robot."""

    robot_id: int
    task_id: int
    task_uid: str


# ─────────────────────────────────────────────────────────────────────────────
class TaskRegistry:
    """Registry in-memory, an toàn khi heartbeat và status chạy khác thread."""

    def __init__(self) -> None:
        """Khởi tạo các index theo robot task và UID runtime."""
        self._lock = threading.RLock()
        self._by_task: Dict[Tuple[int, int], AssignedTask] = {}
        self._by_uid: Dict[str, AssignedTask] = {}
        self._next_task_id: Dict[int, int] = {}

    # ─────────────────────────────────────────────────────────────────────────
    def allocate(
        self,
        robot_id: int,
        task_uid: str,
    ) -> AssignedTask:
        """Cấp task ID còn trống cho một UID runtime duy nhất."""
        with self._lock:
            existing = self._by_uid.get(task_uid)
            if existing is not None:
                return existing
            if any(task.robot_id == robot_id for task in self._by_task.values()):
                raise ValueError(f"Robot {robot_id} đang có task")

            start = self._next_task_id.get(robot_id, TASK_ID_MIN)
            task_id = self._find_available_id(robot_id, start)
            if task_id is None:
                raise TaskRegistryFull(robot_id)

            task = AssignedTask(
                robot_id=robot_id,
                task_id=task_id,
                task_uid=task_uid,
            )
            self._by_task[(robot_id, task_id)] = task
            self._by_uid[task_uid] = task
            self._next_task_id[robot_id] = (
                TASK_ID_MIN + ((task_id + 1) % (TASK_ID_MAX + 1))
            )
            return task

    # ─────────────────────────────────────────────────────────────────────────
    def get(self, robot_id: int, task_id: int) -> Optional[AssignedTask]:
        """Tra task từ định danh robot và task ID."""
        with self._lock:
            return self._by_task.get((robot_id, task_id))

    # ─────────────────────────────────────────────────────────────────────────
    def get_by_uid(self, task_uid: str) -> Optional[AssignedTask]:
        """Tra reservation bằng UID runtime."""
        with self._lock:
            return self._by_uid.get(task_uid)

    # ─────────────────────────────────────────────────────────────────────────
    def release(self, robot_id: int, task_id: int) -> Optional[AssignedTask]:
        """Giải phóng task khỏi toàn bộ index và trả reservation vừa xóa."""
        with self._lock:
            task = self._by_task.pop((robot_id, task_id), None)
            if task is None:
                return None
            self._by_uid.pop(task.task_uid, None)
            return task

    # ─────────────────────────────────────────────────────────────────────────
    def reserved_robot_ids(self) -> List[int]:
        """Trả danh sách robot đang có task để tránh giao task kép."""
        with self._lock:
            return [task.robot_id for task in self._by_task.values()]

    # ─────────────────────────────────────────────────────────────────────────
    def all_tasks(self) -> List[AssignedTask]:
        """Trả snapshot toàn bộ reservation hiện tại."""
        with self._lock:
            return list(self._by_task.values())

    # ─────────────────────────────────────────────────────────────────────────
    def _find_available_id(self, robot_id: int, start: int) -> Optional[int]:
        """Tìm task ID chưa được robot sử dụng, bắt đầu từ vị trí chỉ định."""
        for offset in range(TASK_ID_MAX + 1):
            task_id = (start + offset) % (TASK_ID_MAX + 1)
            if (robot_id, task_id) not in self._by_task:
                return task_id
        return None
