import math
import threading
import time
from typing import List, Optional

from src.models import Zone, ZoneState
from utils import LOGGER


MAX_UART_BYTES = 250
UART_SEND_REPEAT_COUNT = 3
UART_REPEAT_DELAY_SECONDS = 0.3
ROBOT_AT_ZONE_DISTANCE_THRESHOLD = 0.1


def get_uart_zone_id(item: dict) -> str:
    return item.get("zone_key") or item.get("zone_name", "")


def build_uart_string(det_list: list, clr_list: list, is_sync: bool = False) -> str:
    parts = []
    if is_sync:
        parts.append("sync")

    if det_list:
        d_str = "d:" + ";".join([
            f"{get_uart_zone_id(item)},{item['goal_pose'].get('x', 0)},{item['goal_pose'].get('y', 0)},{item['goal_pose'].get('theta', 0)}"
            for item in det_list
        ])
        parts.append(d_str)

    if clr_list:
        c_str = "c:" + ";".join([
            f"{get_uart_zone_id(item)},{item['goal_pose'].get('x', 0)},{item['goal_pose'].get('y', 0)},{item['goal_pose'].get('theta', 0)}"
            for item in clr_list
        ])
        parts.append(c_str)

    return "-".join(parts)


def send_uart_string_repeated(uart, message: str):
    for _ in range(UART_SEND_REPEAT_COUNT):
        threading.Thread(target=uart.send_string, args=(message,), daemon=True).start()
        time.sleep(UART_REPEAT_DELAY_SECONDS)


def send_uart_payload(uart, payload: dict, is_sync: bool = False):
    """Chuyển payload event sang chuỗi UART và chia nhỏ nếu vượt quá giới hạn bytes."""
    if not payload or uart is None:
        return

    detected = payload.get("detected", [])
    cleared = payload.get("cleared", [])
    all_events = [("d", d) for d in detected] + [("c", c) for c in cleared]

    current_det = []
    current_clr = []

    for event_type, event_data in all_events:
        if event_type == "d":
            current_det.append(event_data)
        else:
            current_clr.append(event_data)

        test_str = build_uart_string(current_det, current_clr, is_sync)

        if len(test_str.encode("utf-8")) > MAX_UART_BYTES:
            if event_type == "d":
                current_det.pop()
            else:
                current_clr.pop()

            full_str = build_uart_string(current_det, current_clr, is_sync)
            if full_str:
                send_uart_string_repeated(uart, full_str)

            current_det = [event_data] if event_type == "d" else []
            current_clr = [event_data] if event_type == "c" else []

    final_str = build_uart_string(current_det, current_clr, is_sync)
    if final_str:
        send_uart_string_repeated(uart, final_str)


def build_occupied_zones_sync_payload(zones: List[Zone], latest_received_data: Optional[dict]) -> dict:
    """Tạo payload sync cho các zone đang OCCUPIED, lọc zone robot đang đứng."""
    sync_payload = {
        "detected": [],
        "cleared": []
    }

    robot_x, robot_y = None, None
    if latest_received_data:
        payload = latest_received_data.get("payload", {})
        if isinstance(payload, dict) and "x" in payload and "y" in payload:
            robot_x = payload["x"]
            robot_y = payload["y"]

    for zone in zones:
        if zone.state != ZoneState.OCCUPIED:
            continue

        is_robot_at_zone = False
        if robot_x is not None and robot_y is not None:
            goal_x = zone.goal_pose.get("x", 0.0)
            goal_y = zone.goal_pose.get("y", 0.0)
            distance = math.sqrt((robot_x - goal_x) ** 2 + (robot_y - goal_y) ** 2)

            if distance < ROBOT_AT_ZONE_DISTANCE_THRESHOLD:
                is_robot_at_zone = True
                LOGGER.info(
                    f"Lược bỏ zone {zone.key} khỏi lệnh sync vì robot đang đứng tại đây "
                    f"(khoảng cách: {distance:.2f}m)."
                )

        if not is_robot_at_zone:
            sync_payload["detected"].append({
                "camera_id": zone.camera_id,
                "camera_name": zone.camera_name,
                "zone_key": zone.key,
                "zone_name": zone.name,
                "goal_pose": zone.goal_pose
            })

    return sync_payload
