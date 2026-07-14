"""Kho trạng thái phục vụ toàn cục của người đã được ReID định danh."""

from __future__ import annotations

import threading
from typing import Dict, Optional

from src.dispatch_decision.datatypes import (
    PersonServiceRecord,
    PersonServiceState,
)


# ─────────────────────────────────────────────────────────────────────────────
class PersonServiceStateStore:
    """
    Lưu service theo global ID để ngăn cùng một người được mời nhiều lần.

    REQUESTED chặn task trùng trong khi task hiện tại còn mở. SERVED tiếp tục
    chặn người đó ở mọi zone trong phiên runtime hiện tại.
    """

    def __init__(self) -> None:
        """Khởi tạo một store in-memory an toàn khi truy cập đa luồng."""
        self._lock = threading.RLock()
        self._records: Dict[int, PersonServiceRecord] = {}

    # ─────────────────────────────────────────────────────────────────────────
    def get(self, global_id: int) -> Optional[PersonServiceRecord]:
        """Lấy service record hiện tại của một người nếu có."""
        with self._lock:
            return self._records.get(global_id)

    # ─────────────────────────────────────────────────────────────────────────
    def get_state(self, global_id: int) -> Optional[PersonServiceState]:
        """Lấy trạng thái phục vụ hiện tại của một người nếu có."""
        record = self.get(global_id)
        return None if record is None else record.state

    # ─────────────────────────────────────────────────────────────────────────
    def is_blocked(self, global_id: int) -> bool:
        """Trả True nếu người đã có request hoặc đã được phục vụ xong."""
        with self._lock:
            return global_id in self._records

    # ─────────────────────────────────────────────────────────────────────────
    def mark_requested(self, global_id: int, zone_id: str) -> bool:
        """
        Ghi nhận một người đã được sinh TASK_ASSIGN.

        Trả False và giữ nguyên record nếu người đã bị chặn bởi service khác.
        """
        with self._lock:
            if global_id in self._records:
                return False

            self._records[global_id] = PersonServiceRecord(
                state=PersonServiceState.REQUESTED,
                zone_id=zone_id,
            )
            return True

    # ─────────────────────────────────────────────────────────────────────────
    def mark_served(self, global_id: int, zone_id: str) -> bool:
        """Chuyển request đúng người và đúng zone sang trạng thái SERVED."""
        with self._lock:
            current = self._records.get(global_id)
            if (
                current is None
                or current.state is not PersonServiceState.REQUESTED
                or current.zone_id != zone_id
            ):
                return False

            self._records[global_id] = PersonServiceRecord(
                state=PersonServiceState.SERVED,
                zone_id=zone_id,
            )
            return True

    # ─────────────────────────────────────────────────────────────────────────
    def release_request(self, global_id: int, zone_id: str) -> bool:
        """Bỏ request chưa hoàn thành để người có thể được xét lại về sau."""
        with self._lock:
            current = self._records.get(global_id)
            if (
                current is None
                or current.state is not PersonServiceState.REQUESTED
                or current.zone_id != zone_id
            ):
                return False

            self._records.pop(global_id)
            return True

    # ─────────────────────────────────────────────────────────────────────────
    def clear(self) -> None:
        """Xóa toàn bộ trạng thái người, chủ yếu phục vụ reset runtime và test."""
        with self._lock:
            self._records.clear()
