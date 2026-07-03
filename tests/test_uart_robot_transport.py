import unittest

from src.robot_dispatch import (
    RobotDispatchEvent,
    RobotDispatchRequest,
    build_uart_dispatch_payload,
)
from src.zones_management import ZoneState
from uart.uart_manager import UartManager
from uart.uart_sender import _build_uart_string


class UartRobotTransportTest(unittest.TestCase):
    def test_build_uart_dispatch_payload_uses_detected_and_cleared(self):
        """Payload UART giữ format cũ gồm detected và cleared."""
        occupied = self._make_request(
            request_id="req-occupied",
            event=RobotDispatchEvent.ZONE_OCCUPIED,
            zone_name="zone_1",
        )
        cleared = self._make_request(
            request_id="req-cleared",
            event=RobotDispatchEvent.ZONE_CLEARED,
            zone_name="zone_2",
        )

        payload = build_uart_dispatch_payload([occupied, cleared])

        self.assertEqual(set(payload.keys()), {"detected", "cleared"})
        self.assertEqual(len(payload["detected"]), 1)
        self.assertEqual(len(payload["cleared"]), 1)
        self.assertEqual(payload["detected"][0]["zone_id"], "z1")
        self.assertEqual(payload["cleared"][0]["zone_id"], "z1")
        self.assertEqual(payload["detected"][0]["zone_name"], "zone_1")
        self.assertEqual(payload["cleared"][0]["zone_name"], "zone_2")
        self.assertEqual(payload["detected"][0]["goal_pose"]["x"], 1.0)

    def test_uart_manager_routes_robot_service_feedback(self):
        """UART manager gọi handler khi nhận JSON robot_service."""
        manager = UartManager()
        received = []
        payload = {
            "type": "robot_service",
            "status": "served",
            "zone_id": "z1",
        }

        manager.set_robot_service_handler(received.append)
        manager._handle_received_data(payload)

        self.assertEqual(received, [payload])

    def test_uart_string_uses_zone_id(self):
        """Chuỗi UART dùng zone_id làm định danh zone."""
        message = _build_uart_string(
            [
                {
                    "zone_id": "abc123",
                    "zone_name": "Tiếng Việt",
                    "goal_pose": {"x": 1.0, "y": 2.0, "theta": 0.0},
                }
            ],
            [],
        )

        self.assertEqual(message, "d:abc123,1.0,2.0,0.0")

    def _make_request(
        self,
        *,
        request_id: str,
        event: RobotDispatchEvent,
        zone_name: str,
    ) -> RobotDispatchRequest:
        """Tạo request giả để kiểm tra mapping sang payload UART."""
        return RobotDispatchRequest(
            request_id=request_id,
            event=event,
            camera_id="cam1",
            camera_name="Camera 1",
            zone_id="z1",
            zone_name=zone_name,
            state=ZoneState.OCCUPIED,
            goal_pose={"x": 1.0, "y": 2.0, "theta": 0.0},
            timestamp=100.0,
        )


if __name__ == "__main__":
    unittest.main()
