from dataclasses import dataclass
from typing import Dict, List
from src.models import Zone, ZoneState


@dataclass
class ZoneStateMachine:
    confirm_enter_time: float = 8.0
    confirm_exit_time: float = 8.0
    pending_enter_miss_grace_time: float = 1.5

    def update(self, zones: List[Zone], zone_has_detection: Dict[str, bool], current_time: float) -> dict:
        """
        Cập nhật trạng thái zone dựa trên bbox occupancy và trả về event UART.
        """
        uart_payload = {
            "detected": [],
            "cleared": []
        }

        for zone in zones:
            has_detection = zone_has_detection.get(zone.name, False)

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
                        uart_payload["detected"].append({
                            "zone_name": zone.name,
                            "goal_pose": zone.goal_pose
                        })
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
                elif has_exit_timed_out:
                    uart_payload["cleared"].append({
                        "zone_name": zone.name,
                        "goal_pose": zone.goal_pose
                    })
                    zone.reset_zone()

        return uart_payload
