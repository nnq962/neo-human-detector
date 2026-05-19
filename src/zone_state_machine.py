from dataclasses import dataclass
import time
from typing import Dict, List, Any
from src.models import Zone, ZoneState


@dataclass
class ZoneStateMachine:
    confirm_enter_time: float = 8.0
    confirm_exit_time: float = 8.0
    pending_enter_miss_grace_time: float = 1.5

    def _build_payload(self, zone: Zone, detection_count: int) -> Dict[str, Any]:
        """Hàm helper để đóng gói dữ liệu, tránh lặp code."""
        return {
            "camera_id": zone.camera_id,
            "camera_name": zone.camera_name,
            "zone_key": zone.key,
            "zone_name": zone.name,
            "detection_count": detection_count,
            "goal_pose": zone.goal_pose
        }

    def update(self, zones: List[Zone], zone_counts: Dict[str, int]) -> dict:
        """
        Cập nhật trạng thái cho từng zone dựa trên số bbox hiện có trong zone.
        
        Logic xử lý các trạng thái:
        - EMPTY: Chưa có detection. Nếu zone có bbox -> chuyển sang PENDING_ENTER.
        - PENDING_ENTER: Chờ detection ổn định đủ confirm_enter_time -> OCCUPIED.
        - OCCUPIED: Đã xác nhận có người. Nếu zone không còn bbox -> PENDING_EXIT.
        - PENDING_EXIT: Chờ mất detection đủ confirm_exit_time -> EMPTY/cleared.
          Nếu bbox xuất hiện lại trong thời gian chờ -> quay về OCCUPIED.
          
        Args:
            zones: Danh sách zone thuộc camera hiện tại.
            zone_counts: Mapping zone.key -> số bbox nằm trong zone ở frame hiện tại.
            
        Returns:
            dict: Payload gồm hai danh sách "detected" và "cleared" chứa các event mới phát sinh.
        """

        current_time = time.time()
        uart_payload = {
            "detected": [],
            "cleared": []
        }

        for zone in zones:
            detection_count = zone_counts.get(zone.key, 0)
            has_detection = detection_count > 0

            if zone.state == ZoneState.EMPTY:
                if has_detection:
                    zone.state = ZoneState.PENDING_ENTER
                    zone.enter_time = current_time
                    zone.lost_time = 0.0

            elif zone.state == ZoneState.PENDING_ENTER:
                if has_detection:
                    zone.lost_time = 0.0
                    if current_time - zone.enter_time >= self.confirm_enter_time:
                        zone.state = ZoneState.OCCUPIED
                        uart_payload["detected"].append(self._build_payload(zone, detection_count))
                else:
                    if zone.lost_time == 0.0:
                        zone.lost_time = current_time
                    elif current_time - zone.lost_time >= self.pending_enter_miss_grace_time:
                        zone.reset_zone()

            elif zone.state == ZoneState.OCCUPIED:
                if not has_detection:
                    zone.state = ZoneState.PENDING_EXIT
                    zone.lost_time = current_time

            elif zone.state == ZoneState.PENDING_EXIT:
                has_exit_timed_out = current_time - zone.lost_time >= self.confirm_exit_time

                if has_detection:
                    zone.state = ZoneState.OCCUPIED
                    zone.lost_time = 0.0
                elif has_exit_timed_out:
                    uart_payload["cleared"].append(self._build_payload(zone, detection_count))
                    zone.reset_zone()

        return uart_payload
