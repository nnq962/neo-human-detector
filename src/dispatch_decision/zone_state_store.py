"""Kho trạng thái decision được lưu theo từng zone."""

from __future__ import annotations

import threading
from dataclasses import replace
from typing import Dict, Optional

from src.dispatch_decision.datatypes import (
    ZoneDecisionState,
    ZoneServiceState,
)
from src.zones_management import ZoneState


# ─────────────────────────────────────────────────────────────────────────────
class ZoneDecisionStateStore:
    """
    Lưu trạng thái decision của từng zone.

    Store chỉ có trách nhiệm đọc và cập nhật state. Các rule như
    PENDING_ENTER → OCCUPIED sinh TASK_ASSIGN thuộc về decision engine/policy.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._states: Dict[str, ZoneDecisionState] = {}

    # ─────────────────────────────────────────────────────────────────────
    def get(self, zone_id: str) -> Optional[ZoneDecisionState]:
        """Lấy state hiện tại; trả None nếu zone chưa từng được quan sát."""
        with self._lock:
            return self._states.get(zone_id)

    # ─────────────────────────────────────────────────────────────────────
    def initialize(
        self,
        zone_id: str,
        zone_state: ZoneState,
    ) -> ZoneDecisionState:
        """
        Khởi tạo state cho zone nếu chưa tồn tại.

        Nếu zone đã tồn tại, giữ nguyên và trả state hiện tại.
        """
        with self._lock:
            return self._states.setdefault(
                zone_id,
                ZoneDecisionState(last_zone_state=zone_state),
            )

    # ─────────────────────────────────────────────────────────────────────
    def update(
        self,
        zone_id: str,
        **changes: object,
    ) -> ZoneDecisionState:
        """Cập nhật nhiều field của một zone state trong cùng một lần lock."""
        with self._lock:
            current = self._require_state(zone_id)
            updated = replace(current, **changes)
            self._states[zone_id] = updated
            return updated

    # ─────────────────────────────────────────────────────────────────────
    def get_service_state(self, zone_id: str) -> ZoneServiceState:
        """
        Lấy trạng thái phục vụ của một zone.

        Zone chưa từng được quan sát được xem là chưa yêu cầu phục vụ.
        """
        with self._lock:
            state = self._states.get(zone_id)

            if state is None:
                return ZoneServiceState.NOT_REQUESTED

            return state.service_state

    # ─────────────────────────────────────────────────────────────────────
    def is_awaiting_identity(self, zone_id: str) -> bool:
        """Trả True nếu zone đang chờ một người có global ID."""
        with self._lock:
            state = self._states.get(zone_id)
            return state is not None and state.awaiting_identity

    # ─────────────────────────────────────────────────────────────────────
    def is_awaiting_reassignment(self, zone_id: str) -> bool:
        """Trả True nếu zone đang chờ assign cho người thay thế."""
        with self._lock:
            state = self._states.get(zone_id)
            return state is not None and state.awaiting_reassignment

    # ─────────────────────────────────────────────────────────────────────
    def get_active_person_global_id(self, zone_id: str) -> Optional[int]:
        """Lấy global ID của người đang được zone phục vụ nếu có."""
        with self._lock:
            state = self._states.get(zone_id)
            if state is None:
                return None
            return state.active_person_global_id

    # ─────────────────────────────────────────────────────────────────────
    def remove(self, zone_id: str) -> Optional[ZoneDecisionState]:
        """Xóa state của một zone không còn tồn tại trong cấu hình."""
        with self._lock:
            return self._states.pop(zone_id, None)

    # ─────────────────────────────────────────────────────────────────────
    def clear(self) -> None:
        """Xóa toàn bộ state, chủ yếu phục vụ reset runtime và test."""
        with self._lock:
            self._states.clear()

    # ─────────────────────────────────────────────────────────────────────
    def _require_state(self, zone_id: str) -> ZoneDecisionState:
        """Lấy state bắt buộc phải tồn tại."""
        try:
            return self._states[zone_id]
        except KeyError as exc:
            raise KeyError(
                f"Zone {zone_id!r} chưa được khởi tạo trong zone decision state store"
            ) from exc
