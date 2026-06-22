"""
State machine xử lý vòng đời zone.

Zone chỉ chuyển OCCUPIED sau khi detection ổn định đủ thời gian, và chỉ cleared
sau khi mất detection đủ thời gian xác nhận.
"""

from dataclasses import dataclass
import time
from typing import Mapping, Sequence

from src.zones_management.datatypes import Zone, ZoneState


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ZoneStateMachine:
    """
    Cập nhật trạng thái zone dựa trên số detection hiện nằm trong từng zone.

    Các tham số thời gian tính bằng giây và có thể lấy trực tiếp từ block
    `zone_state_machine` trong YAML config.
    """

    confirm_enter_time: float = 8.0
    confirm_exit_time: float = 8.0
    pending_enter_miss_grace_time: float = 1.5

    def update(
        self,
        zones: Sequence[Zone],
        zone_counts: Mapping[str, int],
    ) -> None:
        """
        Cập nhật state cho từng zone.

        Hàm này chỉ quản lý vòng đời zone. Dữ liệu gửi robot/WebSocket được build
        ở tầng occupancy/output, không nằm trong state machine.
        """
        current_time = time.time()

        for zone in zones:
            has_detection = int(zone_counts.get(zone.key, 0)) > 0

            if zone.state == ZoneState.EMPTY:
                self._handle_empty(zone, has_detection, current_time)
            elif zone.state == ZoneState.PENDING_ENTER:
                self._handle_pending_enter(zone, has_detection, current_time)
            elif zone.state == ZoneState.OCCUPIED:
                self._handle_occupied(zone, has_detection, current_time)
            elif zone.state == ZoneState.PENDING_EXIT:
                self._handle_pending_exit(zone, has_detection, current_time)

    def _handle_empty(self, zone: Zone, has_detection: bool, current_time: float) -> None:
        """EMPTY -> PENDING_ENTER khi bắt đầu có detection trong zone."""
        if not has_detection:
            return

        zone.state = ZoneState.PENDING_ENTER
        zone.enter_time = current_time
        zone.lost_time = 0.0

    def _handle_pending_enter(
        self,
        zone: Zone,
        has_detection: bool,
        current_time: float,
    ) -> None:
        """PENDING_ENTER cần detection đủ ổn định trước khi xác nhận OCCUPIED."""
        if has_detection:
            zone.lost_time = 0.0
            if current_time - zone.enter_time >= self.confirm_enter_time:
                zone.state = ZoneState.OCCUPIED
            return

        if zone.lost_time == 0.0:
            zone.lost_time = current_time
        elif current_time - zone.lost_time >= self.pending_enter_miss_grace_time:
            zone.reset_zone()

    def _handle_occupied(self, zone: Zone, has_detection: bool, current_time: float) -> None:
        """OCCUPIED -> PENDING_EXIT khi zone tạm mất detection."""
        if has_detection:
            return

        zone.state = ZoneState.PENDING_EXIT
        zone.lost_time = current_time

    def _handle_pending_exit(
        self,
        zone: Zone,
        has_detection: bool,
        current_time: float,
    ) -> None:
        """PENDING_EXIT quay lại OCCUPIED nếu thấy người lại, hoặc cleared nếu timeout."""
        if has_detection:
            zone.state = ZoneState.OCCUPIED
            zone.lost_time = 0.0
            return

        if current_time - zone.lost_time >= self.confirm_exit_time:
            zone.reset_zone()
