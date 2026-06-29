"""
Transport gửi batch request robot qua UART theo format cũ.
"""

from __future__ import annotations

from typing import Sequence

from src.robot_dispatch.datatypes import RobotDispatchEvent, RobotDispatchRequest
from utils import LOGGER


# ─────────────────────────────────────────────────────────────────────────────
class UartRobotTransport:
    """Transport chuyển batch robot dispatch thành payload UART detected/cleared."""

    def __init__(self, uart) -> None:
        """Khởi tạo transport với UART manager hiện có."""
        self.uart = uart

    def send_batch(self, requests: Sequence[RobotDispatchRequest]) -> None:
        """Gửi batch request qua UART bằng format detected/cleared cũ."""
        payload = build_uart_dispatch_payload(requests)
        if not payload["detected"] and not payload["cleared"]:
            return

        from uart.uart_sender import send_uart_payload

        LOGGER.info("Robot UART payload: %s", payload)
        send_uart_payload(self.uart, payload)

    def send_sync_payload(self, payload: dict) -> None:
        """Gửi payload sync qua UART với prefix sync."""
        from uart.uart_sender import send_uart_payload

        LOGGER.info("Robot UART sync payload: %s", payload)
        send_uart_payload(self.uart, payload, is_sync=True)

    def close(self) -> None:
        """Đóng transport UART, không đóng UART manager dùng chung."""
        if hasattr(self.uart, "set_sync_handler"):
            self.uart.set_sync_handler(None)


# ─────────────────────────────────────────────────────────────────────────────
def build_uart_dispatch_payload(requests: Sequence[RobotDispatchRequest]) -> dict:
    """Chuyển danh sách request thành payload UART detected/cleared."""
    payload = {
        "detected": [],
        "cleared": [],
    }

    for request in requests:
        item = _build_uart_zone_item(request)

        if request.event == RobotDispatchEvent.ZONE_OCCUPIED:
            payload["detected"].append(item)
        elif request.event == RobotDispatchEvent.ZONE_CLEARED:
            payload["cleared"].append(item)

    return payload


# ─────────────────────────────────────────────────────────────────────────────
def _build_uart_zone_item(request: RobotDispatchRequest) -> dict:
    """Tạo item zone theo format cũ mà UART payload đang dùng."""
    return {
        "camera_id": request.camera_id,
        "camera_name": request.camera_name,
        "zone_key": request.zone_key,
        "zone_name": request.zone_name,
        "goal_pose": dict(request.goal_pose),
    }
