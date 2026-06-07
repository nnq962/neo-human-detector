"""
Module zones gom model, hình học và state machine của vùng giám sát.
"""

from src.zones.geometry import assign_bboxes_to_zones, assign_detections_to_zones, is_bbox_in_zone
from src.zones.models import Zone, ZoneColor, ZoneState
from src.zones.state_machine import ZoneStateMachine, ZoneTransitionPayload

__all__ = [
    "Zone",
    "ZoneColor",
    "ZoneState",
    "ZoneStateMachine",
    "ZoneTransitionPayload",
    "assign_bboxes_to_zones",
    "assign_detections_to_zones",
    "is_bbox_in_zone",
]
