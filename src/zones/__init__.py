"""
Module zones gom model, hình học và state machine của vùng giám sát.
"""

from src.zones.geometry import assign_detections_to_zones, is_bbox_in_zone
from src.zones.models import Zone, ZoneColor, ZoneState
from src.zones.occupancy import (
    IdentityServiceState,
    IdentityServiceStatus,
    RobotServiceRequest,
    ZoneOccupancyManager,
    ZoneOccupancyPolicy,
    ZoneOccupancySnapshot,
    ZoneOccupant,
    build_zone_occupancy_snapshot,
)
from src.zones.state_machine import ZoneStateMachine, ZoneTransitionPayload

__all__ = [
    "IdentityServiceState",
    "IdentityServiceStatus",
    "RobotServiceRequest",
    "Zone",
    "ZoneColor",
    "ZoneOccupancyManager",
    "ZoneOccupancyPolicy",
    "ZoneOccupancySnapshot",
    "ZoneOccupant",
    "ZoneState",
    "ZoneStateMachine",
    "ZoneTransitionPayload",
    "assign_detections_to_zones",
    "build_zone_occupancy_snapshot",
    "is_bbox_in_zone",
]
