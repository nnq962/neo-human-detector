"""
Module zones gom model, hình học và state machine của vùng giám sát.
"""

from src.zones_management.datatypes import Zone, ZoneColor, ZoneState
from src.zones_management.geometry import assign_detections_to_zones, is_point_in_zone
from src.zones_management.state_machine import ZoneStateMachine

__all__ = [
    "Zone",
    "ZoneColor",
    "ZoneState",
    "ZoneStateMachine",
    "assign_detections_to_zones",
    "is_point_in_zone",
]
