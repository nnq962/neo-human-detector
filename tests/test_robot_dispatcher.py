import unittest

import numpy as np

from src.robot_dispatch import (
    InMemoryRobotTransport,
    RobotDispatchConfig,
    RobotDispatchEvent,
    RobotDispatcher,
)
from src.zones_management import Zone, ZoneState


class RobotDispatcherTest(unittest.TestCase):
    def test_occupied_transition_emits_once(self):
        """Dispatcher chỉ phát một request khi zone vừa chuyển OCCUPIED."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True),
            transport=transport,
        )
        zone = self._make_zone()

        self.assertEqual(dispatcher.process_zones([zone], timestamp=100.0), [])

        zone.state = ZoneState.PENDING_ENTER
        self.assertEqual(dispatcher.process_zones([zone], timestamp=101.0), [])

        zone.state = ZoneState.OCCUPIED
        emitted = dispatcher.process_zones([zone], timestamp=102.0)
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0].event, RobotDispatchEvent.ZONE_OCCUPIED)

        self.assertEqual(dispatcher.process_zones([zone], timestamp=103.0), [])
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(len(transport.batches), 1)

    def test_cleared_transition_is_optional(self):
        """Dispatcher chỉ phát event cleared khi cấu hình cho phép."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True, emit_cleared=True),
            transport=transport,
        )
        zone = self._make_zone()

        zone.state = ZoneState.OCCUPIED
        dispatcher.process_zones([zone], timestamp=100.0)

        zone.state = ZoneState.PENDING_EXIT
        self.assertEqual(dispatcher.process_zones([zone], timestamp=101.0), [])

        zone.state = ZoneState.EMPTY
        emitted = dispatcher.process_zones([zone], timestamp=102.0)
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0].event, RobotDispatchEvent.ZONE_CLEARED)

    def test_multiple_occupied_zones_are_sent_as_one_batch(self):
        """Nhiều zone cùng chuyển OCCUPIED được gửi trong một batch."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True),
            transport=transport,
        )
        zones = [
            self._make_zone(name=f"zone_{index}", zone_id=f"z{index}")
            for index in range(5)
        ]

        dispatcher.process_zones(zones, timestamp=100.0)
        for zone in zones:
            zone.state = ZoneState.OCCUPIED

        emitted = dispatcher.process_zones(zones, timestamp=101.0)

        self.assertEqual(len(emitted), 5)
        self.assertEqual(len(transport.requests), 5)
        self.assertEqual(len(transport.batches), 1)
        self.assertEqual(len(transport.batches[0]), 5)

    def test_pending_exit_back_to_occupied_does_not_emit_again(self):
        """Zone mất detection tạm rồi quay lại OCCUPIED không tạo request mới."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True),
            transport=transport,
        )
        zone = self._make_zone()

        dispatcher.process_zones([zone], timestamp=100.0)
        zone.state = ZoneState.OCCUPIED
        self.assertEqual(len(dispatcher.process_zones([zone], timestamp=101.0)), 1)

        zone.state = ZoneState.PENDING_EXIT
        self.assertEqual(dispatcher.process_zones([zone], timestamp=102.0), [])

        zone.state = ZoneState.OCCUPIED
        self.assertEqual(dispatcher.process_zones([zone], timestamp=103.0), [])
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(len(transport.batches), 1)

    def test_send_sync_uses_latest_confirmed_zone_snapshot(self):
        """Sync gửi lại trạng thái xác nhận mới nhất của các zone."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True),
            transport=transport,
        )
        occupied = self._make_zone(name="occupied", zone_id="z1")
        empty = self._make_zone(name="empty", zone_id="z2")
        pending = self._make_zone(name="pending", zone_id="z3")
        occupied.state = ZoneState.OCCUPIED
        empty.state = ZoneState.EMPTY
        pending.state = ZoneState.PENDING_ENTER

        dispatcher.process_zones([occupied, empty, pending], timestamp=100.0)
        payload = dispatcher.send_sync()

        self.assertEqual(len(payload["detected"]), 1)
        self.assertEqual(payload["detected"][0]["zone_name"], "occupied")
        self.assertEqual(len(payload["cleared"]), 1)
        self.assertEqual(payload["cleared"][0]["zone_name"], "empty")
        self.assertEqual(transport.sync_payloads[-1], payload)

    def test_sync_skips_zone_where_robot_is_already_standing(self):
        """Sync không gửi zone OCCUPIED nếu robot đang đứng tại goal_pose."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True),
            transport=transport,
        )
        zone = self._make_zone()
        zone.state = ZoneState.OCCUPIED

        dispatcher.process_zones([zone], timestamp=100.0)
        payload = dispatcher.send_sync(
            {
                "payload": {
                    "x": 1.0,
                    "y": 2.0,
                }
            }
        )

        self.assertEqual(payload["detected"], [])
        self.assertEqual(payload["cleared"], [])

    def _make_zone(self, name: str = "zone_a", zone_id: str = "z1") -> Zone:
        """Tạo zone giả tối thiểu cho test dispatcher."""
        return Zone(
            camera_id="cam1",
            camera_name="Camera 1",
            name=name,
            id=zone_id,
            pts=np.zeros((4, 2)),
            goal_pose={"x": 1.0, "y": 2.0, "theta": 0.0},
        )


if __name__ == "__main__":
    unittest.main()
