import unittest
from unittest.mock import patch

import numpy as np

from src.detection.datatypes import Detection, InferenceFrame
from src.robot_dispatch import (
    InMemoryRobotTransport,
    RobotDispatchConfig,
    RobotDispatchEvent,
    RobotDispatcher,
    robot_dispatch_events,
)
from src.zones_management import Zone, ZoneState


class RobotDispatcherTest(unittest.TestCase):
    def setUp(self):
        robot_dispatch_events.clear()

    def test_occupied_transition_emits_once(self):
        """Dispatcher chỉ phát một request khi zone vừa chuyển OCCUPIED."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True, require_reid=False),
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
            config=RobotDispatchConfig(enabled=True, emit_cleared=True, require_reid=False),
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
            config=RobotDispatchConfig(enabled=True, require_reid=False),
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
            config=RobotDispatchConfig(enabled=True, require_reid=False),
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

    def test_identity_required_waits_for_global_id(self):
        """Khi cần ReID, zone OCCUPIED chưa có global_id thì chưa gửi request."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True),
            transport=transport,
        )
        zone = self._make_zone()
        zone.state = ZoneState.OCCUPIED
        frame = InferenceFrame(
            detections=[
                Detection(
                    bbox=(0, 0, 10, 10),
                    confidence=0.9,
                )
            ]
        )

        emitted = dispatcher.process_zones(
            [zone],
            timestamp=100.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )

        self.assertEqual(emitted, [])
        self.assertEqual(transport.requests, [])

    def test_identity_required_emits_once_and_marks_requested(self):
        """Người có global_id trong zone OCCUPIED chỉ được request một lần."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True),
            transport=transport,
        )
        zone = self._make_zone()
        zone.state = ZoneState.OCCUPIED
        frame = InferenceFrame(
            detections=[
                Detection(
                    bbox=(0, 0, 10, 10),
                    confidence=0.9,
                    global_id=7,
                    similarity=0.88,
                    track_id=12,
                    status="matched",
                )
            ]
        )

        first = dispatcher.process_zones(
            [zone],
            timestamp=100.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )
        second = dispatcher.process_zones(
            [zone],
            timestamp=101.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].person_global_id, 7)
        self.assertEqual(first[0].similarity, 0.88)
        self.assertEqual(second, [])
        self.assertEqual(dispatcher.get_person_service_states()[7], "REQUESTED")

    def test_robot_dispatch_event_for_identity_invite(self):
        """Websocket event invite có zone và global_id khi gửi request ReID."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True),
            transport=transport,
        )
        zone = self._make_zone()
        zone.state = ZoneState.OCCUPIED
        frame = InferenceFrame(
            detections=[
                Detection(
                    bbox=(0, 0, 10, 10),
                    confidence=0.9,
                    global_id=7,
                    similarity=0.88,
                    track_id=12,
                    status="matched",
                )
            ]
        )

        dispatcher.process_zones(
            [zone],
            timestamp=100.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )

        events = robot_dispatch_events.get_events_after(0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "sent")
        self.assertEqual(events[0]["action"], "invite")
        self.assertEqual(events[0]["zone"]["zone_id"], zone.id)
        self.assertEqual(events[0]["person"]["global_id"], 7)
        self.assertEqual(events[0]["person"]["track_id"], 12)
        self.assertEqual(events[0]["person"]["similarity"], 0.88)

    def test_requested_person_staying_in_same_zone_does_not_publish_skip(self):
        """Người đã request đứng yên trong cùng zone không tạo skip ở frame kế tiếp."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True),
            transport=transport,
        )
        zone = self._make_zone()
        zone.state = ZoneState.OCCUPIED
        frame = InferenceFrame(
            detections=[
                Detection(
                    bbox=(0, 0, 10, 10),
                    confidence=0.9,
                    global_id=7,
                )
            ]
        )

        first = dispatcher.process_zones(
            [zone],
            timestamp=100.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )
        second = dispatcher.process_zones(
            [zone],
            timestamp=101.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )

        events = robot_dispatch_events.get_events_after(0)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "sent")
        self.assertEqual(events[0]["action"], "invite")

    def test_served_person_reentering_same_cleared_zone_publishes_skip(self):
        """Người đã SERVED rời zone về EMPTY rồi vào lại cùng zone sẽ tạo skip."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True),
            transport=transport,
        )
        zone = self._make_zone()
        zone.state = ZoneState.OCCUPIED
        frame = InferenceFrame(
            detections=[
                Detection(
                    bbox=(0, 0, 10, 10),
                    confidence=0.9,
                    global_id=7,
                )
            ]
        )

        dispatcher.process_zones(
            [zone],
            timestamp=100.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )
        dispatcher.handle_robot_service_feedback({
            "type": "robot_service",
            "status": "served",
            "zone_id": zone.id,
        })
        zone.state = ZoneState.EMPTY
        dispatcher.process_zones(
            [zone],
            timestamp=101.0,
            detection_frame=InferenceFrame(detections=[]),
            zone_names=[],
            reid_enabled=True,
        )
        zone.state = ZoneState.PENDING_ENTER
        dispatcher.process_zones(
            [zone],
            timestamp=102.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )
        zone.state = ZoneState.OCCUPIED
        dispatcher.process_zones(
            [zone],
            timestamp=103.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )

        events = robot_dispatch_events.get_events_after(0)
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0]["type"], "sent")
        self.assertEqual(events[1]["type"], "service_update")
        self.assertEqual(events[1]["action"], "served")
        self.assertEqual(events[2]["type"], "skipped")
        self.assertEqual(events[2]["action"], "invite")
        self.assertEqual(events[2]["reason"], "already_served")
        self.assertEqual(events[2]["zone"]["zone_id"], zone.id)
        self.assertEqual(events[2]["person"]["global_id"], 7)

    def test_requested_person_reentering_same_cleared_zone_emits_again(self):
        """Người mới REQUESTED rời zone về EMPTY rồi vào lại cùng global_id sẽ gửi invite lại."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True),
            transport=transport,
        )
        zone = self._make_zone()
        zone.state = ZoneState.OCCUPIED
        frame = InferenceFrame(
            detections=[
                Detection(
                    bbox=(0, 0, 10, 10),
                    confidence=0.9,
                    global_id=7,
                )
            ]
        )

        dispatcher.process_zones(
            [zone],
            timestamp=100.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )
        zone.state = ZoneState.EMPTY
        dispatcher.process_zones(
            [zone],
            timestamp=101.0,
            detection_frame=InferenceFrame(detections=[]),
            zone_names=[],
            reid_enabled=True,
        )
        zone.state = ZoneState.PENDING_ENTER
        dispatcher.process_zones(
            [zone],
            timestamp=102.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )
        zone.state = ZoneState.OCCUPIED
        emitted = dispatcher.process_zones(
            [zone],
            timestamp=103.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )

        events = robot_dispatch_events.get_events_after(0)
        self.assertEqual(len(emitted), 1)
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["type"], "sent")
        self.assertEqual(events[1]["type"], "sent")

    def test_serving_person_reentering_same_cleared_zone_emits_again(self):
        """Người đang SERVING rời zone rồi quay lại thì gửi invite lại."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True),
            transport=transport,
        )
        zone = self._make_zone()
        zone.state = ZoneState.OCCUPIED
        frame = InferenceFrame(
            detections=[
                Detection(
                    bbox=(0, 0, 10, 10),
                    confidence=0.9,
                    global_id=7,
                )
            ]
        )

        dispatcher.process_zones(
            [zone],
            timestamp=100.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )
        dispatcher.handle_robot_service_feedback({
            "type": "robot_service",
            "status": "serving",
            "zone_id": zone.id,
        })
        zone.state = ZoneState.EMPTY
        dispatcher.process_zones(
            [zone],
            timestamp=101.0,
            detection_frame=InferenceFrame(detections=[]),
            zone_names=[],
            reid_enabled=True,
        )
        zone.state = ZoneState.PENDING_ENTER
        dispatcher.process_zones(
            [zone],
            timestamp=102.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )
        zone.state = ZoneState.OCCUPIED
        emitted = dispatcher.process_zones(
            [zone],
            timestamp=103.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )

        events = robot_dispatch_events.get_events_after(0)
        self.assertEqual(len(emitted), 1)
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(events[-1]["type"], "sent")
        self.assertEqual(events[-1]["action"], "invite")

    def test_robot_service_feedback_updates_state_by_zone_id(self):
        """Feedback robot_service không có global_id vẫn update record mới nhất của zone_id."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True),
            transport=transport,
        )
        zone = self._make_zone()
        zone.state = ZoneState.OCCUPIED
        frame = InferenceFrame(
            detections=[
                Detection(
                    bbox=(0, 0, 10, 10),
                    confidence=0.9,
                    global_id=7,
                )
            ]
        )

        dispatcher.process_zones(
            [zone],
            timestamp=100.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )

        dispatcher.handle_robot_service_feedback({
            "type": "robot_service",
            "status": "serving",
            "zone_id": zone.id,
        })
        self.assertEqual(dispatcher.get_person_service_states()[7], "SERVING")

        dispatcher.handle_robot_service_feedback({
            "type": "robot_service",
            "status": "served",
            "zone_id": zone.id,
        })
        self.assertEqual(dispatcher.get_person_service_states()[7], "SERVED")

        dispatcher.handle_robot_service_feedback({
            "type": "robot_service",
            "status": "failed",
            "zone_id": zone.id,
            "reason": "blocked_path",
        })
        self.assertEqual(dispatcher.get_person_service_states()[7], "FAILED")

        events = robot_dispatch_events.get_events_after(0)
        self.assertEqual(events[1]["type"], "service_update")
        self.assertEqual(events[1]["action"], "serving")
        self.assertEqual(events[1]["zone"]["zone_id"], zone.id)
        self.assertEqual(events[1]["person"]["global_id"], 7)
        self.assertEqual(events[2]["action"], "served")
        self.assertEqual(events[3]["action"], "failed")
        self.assertEqual(events[3]["reason"], "blocked_path")

    def test_robot_service_feedback_state_blocks_duplicate_requests(self):
        """SERVING/SERVED/FAILED không làm dispatcher gửi lại cùng global_id mỗi frame."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True),
            transport=transport,
        )
        zone = self._make_zone()
        zone.state = ZoneState.OCCUPIED
        frame = InferenceFrame(
            detections=[
                Detection(
                    bbox=(0, 0, 10, 10),
                    confidence=0.9,
                    global_id=7,
                )
            ]
        )

        dispatcher.process_zones(
            [zone],
            timestamp=100.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )

        for status in ["serving", "served", "failed"]:
            dispatcher.handle_robot_service_feedback({
                "type": "robot_service",
                "status": status,
                "zone_id": zone.id,
            })
            emitted = dispatcher.process_zones(
                [zone],
                timestamp=101.0,
                detection_frame=frame,
                zone_names=[zone.name],
                reid_enabled=True,
            )
            self.assertEqual(emitted, [])

        self.assertEqual(len(transport.requests), 1)

    def test_requested_person_in_another_zone_emits_again(self):
        """Cùng global_id sang zone khác vẫn gửi invite nếu chưa SERVED."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True),
            transport=transport,
        )
        zone_a = self._make_zone(name="zone_a", zone_id="z1")
        zone_b = self._make_zone(name="zone_b", zone_id="z2")
        zone_a.state = ZoneState.OCCUPIED
        zone_b.state = ZoneState.OCCUPIED
        frame = InferenceFrame(
            detections=[
                Detection(
                    bbox=(0, 0, 10, 10),
                    confidence=0.9,
                    global_id=7,
                )
            ]
        )

        first = dispatcher.process_zones(
            [zone_a],
            timestamp=100.0,
            detection_frame=frame,
            zone_names=[zone_a.name],
            reid_enabled=True,
        )
        second = dispatcher.process_zones(
            [zone_b],
            timestamp=101.0,
            detection_frame=frame,
            zone_names=[zone_b.name],
            reid_enabled=True,
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(len(robot_dispatch_events.get_events_after(0)), 2)

    def test_robot_dispatch_event_for_already_served_skip(self):
        """Websocket event skip có zone và global_id đã SERVED."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True),
            transport=transport,
        )
        zone_a = self._make_zone(name="zone_a", zone_id="z1")
        zone_b = self._make_zone(name="zone_b", zone_id="z2")
        zone_a.state = ZoneState.OCCUPIED
        zone_b.state = ZoneState.OCCUPIED
        frame = InferenceFrame(
            detections=[
                Detection(
                    bbox=(0, 0, 10, 10),
                    confidence=0.9,
                    global_id=7,
                )
            ]
        )

        dispatcher.process_zones(
            [zone_a],
            timestamp=100.0,
            detection_frame=frame,
            zone_names=[zone_a.name],
            reid_enabled=True,
        )
        dispatcher.handle_robot_service_feedback({
            "type": "robot_service",
            "status": "served",
            "zone_id": zone_a.id,
        })
        dispatcher.process_zones(
            [zone_b],
            timestamp=101.0,
            detection_frame=frame,
            zone_names=[zone_b.name],
            reid_enabled=True,
        )

        events = robot_dispatch_events.get_events_after(0)
        self.assertEqual(len(events), 3)
        self.assertEqual(events[2]["type"], "skipped")
        self.assertEqual(events[2]["action"], "invite")
        self.assertEqual(events[2]["reason"], "already_served")
        self.assertEqual(events[2]["zone"]["zone_id"], zone_b.id)
        self.assertEqual(events[2]["person"]["global_id"], 7)
        self.assertEqual(events[2]["existing_request"]["state"], "SERVED")

    def test_fallback_without_reid_allows_zone_request(self):
        """Fallback cho phép gửi zone-only khi chưa có global_id."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(
                enabled=True,
                fallback_without_reid=True,
            ),
            transport=transport,
        )
        zone = self._make_zone()
        zone.state = ZoneState.OCCUPIED
        frame = InferenceFrame(
            detections=[
                Detection(
                    bbox=(0, 0, 10, 10),
                    confidence=0.9,
                )
            ]
        )

        emitted = dispatcher.process_zones(
            [zone],
            timestamp=100.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )

        self.assertEqual(len(emitted), 1)
        self.assertIsNone(emitted[0].person_global_id)

    def test_fallback_zone_request_prevents_late_identity_duplicate(self):
        """Zone đã fallback request thì không gửi thêm khi global_id xuất hiện muộn."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(
                enabled=True,
                fallback_without_reid=True,
            ),
            transport=transport,
        )
        zone = self._make_zone()
        zone.state = ZoneState.OCCUPIED
        pending_frame = InferenceFrame(
            detections=[
                Detection(
                    bbox=(0, 0, 10, 10),
                    confidence=0.9,
                )
            ]
        )
        identified_frame = InferenceFrame(
            detections=[
                Detection(
                    bbox=(0, 0, 10, 10),
                    confidence=0.9,
                    global_id=7,
                )
            ]
        )

        first = dispatcher.process_zones(
            [zone],
            timestamp=100.0,
            detection_frame=pending_frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )
        second = dispatcher.process_zones(
            [zone],
            timestamp=101.0,
            detection_frame=identified_frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )

        self.assertEqual(len(first), 1)
        self.assertIsNone(first[0].person_global_id)
        self.assertEqual(second, [])
        self.assertEqual(len(transport.requests), 1)

    def test_service_ttl_allows_requesting_person_again(self):
        """Hết TTL thì cùng global_id có thể được request lại."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(
                enabled=True,
                service_ttl_minutes=0.01,
            ),
            transport=transport,
        )
        zone = self._make_zone()
        zone.state = ZoneState.OCCUPIED
        frame = InferenceFrame(
            detections=[
                Detection(
                    bbox=(0, 0, 10, 10),
                    confidence=0.9,
                    global_id=7,
                )
            ]
        )

        first = dispatcher.process_zones(
            [zone],
            timestamp=100.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )
        second = dispatcher.process_zones(
            [zone],
            timestamp=100.5,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )
        third = dispatcher.process_zones(
            [zone],
            timestamp=101.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(len(third), 1)
        self.assertEqual(len(transport.requests), 2)

    def test_service_ttl_allows_served_person_again(self):
        """Người đã SERVED hết TTL thì có thể được mời lại."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(
                enabled=True,
                service_ttl_minutes=0.01,
            ),
            transport=transport,
        )
        zone = self._make_zone()
        zone.state = ZoneState.OCCUPIED
        frame = InferenceFrame(
            detections=[
                Detection(
                    bbox=(0, 0, 10, 10),
                    confidence=0.9,
                    global_id=7,
                )
            ]
        )

        first = dispatcher.process_zones(
            [zone],
            timestamp=100.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )
        with patch("src.robot_dispatch.dispatcher.time.time", return_value=100.0):
            dispatcher.handle_robot_service_feedback({
                "type": "robot_service",
                "status": "served",
                "zone_id": zone.id,
            })

        blocked = dispatcher.process_zones(
            [zone],
            timestamp=100.5,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )
        expired = dispatcher.process_zones(
            [zone],
            timestamp=101.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(blocked, [])
        self.assertEqual(len(expired), 1)
        self.assertEqual(len(transport.requests), 2)

    def test_send_sync_uses_latest_confirmed_zone_snapshot(self):
        """Sync gửi lại trạng thái xác nhận mới nhất của các zone."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True, require_reid=False),
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

    def test_robot_dispatch_event_for_clear_reuses_last_invited_person(self):
        """Websocket event clear có lại global_id nếu zone từng invite bằng ReID."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True, emit_cleared=True),
            transport=transport,
        )
        zone = self._make_zone()
        zone.state = ZoneState.OCCUPIED
        frame = InferenceFrame(
            detections=[
                Detection(
                    bbox=(0, 0, 10, 10),
                    confidence=0.9,
                    global_id=7,
                )
            ]
        )

        dispatcher.process_zones(
            [zone],
            timestamp=100.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )
        zone.state = ZoneState.PENDING_EXIT
        dispatcher.process_zones(
            [zone],
            timestamp=101.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )
        zone.state = ZoneState.EMPTY
        dispatcher.process_zones(
            [zone],
            timestamp=102.0,
            detection_frame=frame,
            zone_names=[zone.name],
            reid_enabled=True,
        )

        events = robot_dispatch_events.get_events_after(0)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1]["type"], "sent")
        self.assertEqual(events[1]["action"], "clear")
        self.assertEqual(events[1]["zone"]["zone_id"], zone.id)
        self.assertEqual(events[1]["zone"]["state"], "EMPTY")
        self.assertEqual(events[1]["person"]["global_id"], 7)

    def test_sync_skips_zone_where_robot_is_already_standing(self):
        """Sync không gửi zone OCCUPIED nếu robot đang đứng tại goal_pose."""
        transport = InMemoryRobotTransport()
        dispatcher = RobotDispatcher(
            config=RobotDispatchConfig(enabled=True, require_reid=False),
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
