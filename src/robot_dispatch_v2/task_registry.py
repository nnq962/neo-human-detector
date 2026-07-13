"""Cấp task id và lưu quan hệ giữa robot task với zone."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


TASK_ID_MIN = 0
TASK_ID_MAX = 255


# ────────────────────────────────────────────────────────────────────────────
class TaskRegistryFull(RuntimeError):
    """Robot đã dùng hết toàn bộ task id có thể biểu diễn bằng uint8."""

    def __init__(self, robot_id: int) -> None:
        self.robot_id = robot_id
        super().__init__(f"Robot {robot_id} đã dùng hết task_id từ 0 đến 255")


# ───────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class AssignedTask:
    """Một task đã được giữ chỗ cho robot và zone."""

    robot_id: int
    task_id: int
    zone_id: str


# ───────────────────────────────────────────────────────────────────────────
class TaskRegistry:
    """Registry in-memory, an toàn khi heartbeat và status chạy khác thread."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_task: Dict[Tuple[int, int], AssignedTask] = {}
        self._by_zone: Dict[str, AssignedTask] = {}
        self._next_task_id: Dict[int, int] = {}

    def allocate(self, robot_id: int, zone_id: str) -> AssignedTask:
        """Cấp task id còn trống; mỗi zone và robot chỉ có tối đa một task."""
        with self._lock:
            existing = self._by_zone.get(zone_id)
            if existing is not None:
                return existing

            if any(task.robot_id == robot_id for task in self._by_task.values()):
                raise ValueError(f"Robot {robot_id} đang có task")

            start = self._next_task_id.get(robot_id, TASK_ID_MIN)
            task_id = self._find_available_id(robot_id, start)
            if task_id is None:
                raise TaskRegistryFull(robot_id)

            task = AssignedTask(robot_id=robot_id, task_id=task_id, zone_id=zone_id)
            self._by_task[(robot_id, task_id)] = task
            self._by_zone[zone_id] = task
            self._next_task_id[robot_id] = TASK_ID_MIN + ((task_id + 1) % (TASK_ID_MAX + 1))
            return task

    def get(self, robot_id: int, task_id: int) -> Optional[AssignedTask]:
        """Tra task từ định danh có trong TaskStatus."""
        with self._lock:
            return self._by_task.get((robot_id, task_id))

    def get_by_zone(self, zone_id: str) -> Optional[AssignedTask]:
        """Tra task đang giữ chỗ cho một zone."""
        with self._lock:
            return self._by_zone.get(zone_id)

    def release(self, robot_id: int, task_id: int) -> Optional[AssignedTask]:
        """Xóa task khỏi cả hai index và trả task vừa xóa."""
        with self._lock:
            task = self._by_task.pop((robot_id, task_id), None)
            if task is not None:
                self._by_zone.pop(task.zone_id, None)
            return task

    def reserved_robot_ids(self) -> List[int]:
        """Danh sách robot đang có task, dùng để tránh giao task kép."""
        with self._lock:
            return [task.robot_id for task in self._by_task.values()]

    def all_tasks(self) -> List[AssignedTask]:
        """Snapshot toàn bộ task hiện tại."""
        with self._lock:
            return list(self._by_task.values())

    def _find_available_id(self, robot_id: int, start: int) -> Optional[int]:
        for offset in range(TASK_ID_MAX + 1):
            task_id = (start + offset) % (TASK_ID_MAX + 1)
            if (robot_id, task_id) not in self._by_task:
                return task_id
        return None
