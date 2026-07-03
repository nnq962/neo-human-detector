"""
Realtime robot dispatch events for websocket consumers.
"""

from __future__ import annotations

from collections import deque
import copy
import threading
import time
from typing import Optional

from src.robot_dispatch.datatypes import RobotDispatchEvent, RobotDispatchRequest
from src.zones_management import Zone


DEFAULT_EVENT_BUFFER_SIZE = 1000


class RobotDispatchEventStore:
    """Thread-safe ring buffer for robot dispatch UI events."""

    def __init__(self, event_buffer_size: int = DEFAULT_EVENT_BUFFER_SIZE) -> None:
        self._lock = threading.RLock()
        self._events = deque(maxlen=event_buffer_size)
        self._event_sequence = 0

    def publish_sent(
        self,
        request: RobotDispatchRequest,
        *,
        person: Optional[dict] = None,
    ) -> dict:
        """Publish a robot request that was sent to the transport."""
        return self._publish(
            {
                "type": "sent",
                "action": _action_from_request(request),
                "request_id": request.request_id,
                "zone": _zone_from_request(request),
                "person": copy.deepcopy(person),
            },
        )

    def publish_skipped_already_served(
        self,
        *,
        global_id: int,
        zone: Zone,
        existing_request: Optional[dict] = None,
    ) -> dict:
        """Publish a skipped invite because the person was already served."""
        payload = {
            "type": "skipped",
            "action": "invite",
            "reason": "already_served",
            "zone": _zone_from_zone(zone),
            "person": {
                "global_id": global_id,
            },
        }
        if existing_request is not None:
            payload["existing_request"] = copy.deepcopy(existing_request)

        return self._publish(payload)

    def publish_service_update(
        self,
        *,
        status: str,
        zone: dict,
        person: Optional[dict],
        request_id: str,
        reason: Optional[str] = None,
    ) -> dict:
        """Publish robot service lifecycle feedback for a zone/person."""
        payload = {
            "type": "service_update",
            "action": status,
            "request_id": request_id,
            "zone": copy.deepcopy(zone),
            "person": copy.deepcopy(person),
        }
        if reason:
            payload["reason"] = reason

        return self._publish(payload)

    def get_event_sequence(self) -> int:
        """Return the latest event sequence."""
        with self._lock:
            return self._event_sequence

    def get_events_after(self, sequence: int, limit: int = 100) -> list[dict]:
        """Return events with sequence greater than the known sequence."""
        with self._lock:
            events = [
                event
                for event in self._events
                if event["sequence"] > sequence
            ]

        return copy.deepcopy(events[:limit])

    def clear(self) -> None:
        """Clear buffered events, mostly for tests."""
        with self._lock:
            self._events.clear()
            self._event_sequence = 0

    def _publish(self, event: dict, *, timestamp: Optional[float] = None) -> dict:
        payload = {
            "sequence": None,
            "timestamp": time.time() if timestamp is None else float(timestamp),
            **event,
        }

        with self._lock:
            self._event_sequence += 1
            payload["sequence"] = self._event_sequence
            self._events.append(payload)

        return copy.deepcopy(payload)


def _action_from_request(request: RobotDispatchRequest) -> str:
    if request.event == RobotDispatchEvent.ZONE_OCCUPIED:
        return "invite"
    if request.event == RobotDispatchEvent.ZONE_CLEARED:
        return "clear"
    return request.event.value


def _zone_from_request(request: RobotDispatchRequest) -> dict:
    return {
        "camera_id": request.camera_id,
        "camera_name": request.camera_name,
        "zone_id": request.zone_id,
        "zone_name": request.zone_name,
        "state": request.state.value,
    }


def _zone_from_zone(zone: Zone) -> dict:
    return {
        "camera_id": zone.camera_id,
        "camera_name": zone.camera_name,
        "zone_id": zone.id,
        "zone_name": zone.name,
        "state": zone.state.value,
    }


robot_dispatch_events = RobotDispatchEventStore()
