"""
Camera config model và loader từ YAML.

Module này chịu trách nhiệm parse camera config và dựng Zone tương ứng.
Việc đọc stream (RTSP) được xử lý ở tầng khác bởi MediaSources.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, List, Optional, Set

import numpy as np

from src.zones_management.datatypes import Zone
from utils import LOGGER


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Camera:
    """Camera runtime dùng trong pipeline AI."""

    id      : str
    name    : str
    source  : str
    zones   : List[Zone] = field(default_factory=list)
    enabled : bool = True

    @property
    def zone_count(self) -> int:
        return len(self.zones)

    def is_ready_for_detection(self) -> bool:
        return self.enabled and bool(self.id) and bool(self.source)


# ─────────────────────────────────────────────────────────────────────────────
def load_cameras_from_config(
    config: Mapping[str, Any],
    *,
    enabled_only: bool = True,
    warn_on_empty_zones: bool = True,
) -> List[Camera]:
    """Parse danh sách camera từ config root."""
    cameras_data = config.get("cameras") or []
    if not isinstance(cameras_data, list):
        LOGGER.warning("Config field 'cameras' không phải list, bỏ qua.")
        return []

    cameras: List[Camera] = []
    seen_camera_ids: Set[str] = set()
    seen_zone_keys: Set[str] = set()

    for camera_data in cameras_data:
        camera = _parse_camera(
            camera_data,
            seen_camera_ids=seen_camera_ids,
            seen_zone_keys=seen_zone_keys,
            enabled_only=enabled_only,
            warn_on_empty_zones=warn_on_empty_zones,
        )
        if camera is not None:
            cameras.append(camera)

    return cameras


# ─────────────────────────────────────────────────────────────────────────────
def _parse_camera(
    camera_data: Any,
    *,
    seen_camera_ids: Set[str],
    seen_zone_keys: Set[str],
    enabled_only: bool,
    warn_on_empty_zones: bool,
) -> Optional[Camera]:
    if not isinstance(camera_data, Mapping):
        LOGGER.warning("Bỏ qua camera config không phải dict: %s", camera_data)
        return None

    enabled = bool(camera_data.get("enabled", True))
    if enabled_only and not enabled:
        return None

    camera_id   = str(camera_data.get("id")   or "").strip()
    camera_name = str(camera_data.get("name") or camera_id).strip()

    if not camera_id:
        LOGGER.warning("Bỏ qua camera thiếu id: %s", camera_data)
        return None

    stream_data = camera_data.get("stream") or {}
    if not isinstance(stream_data, Mapping):
        stream_data = {}

    source = str(stream_data.get("source") or "").strip()
    if not source:
        LOGGER.warning("Bỏ qua camera '%s' thiếu stream.source.", camera_name)
        return None

    if camera_id in seen_camera_ids:
        LOGGER.warning("Bỏ qua camera trùng id '%s'.", camera_id)
        return None

    zones = _parse_zones(
        camera_id=camera_id,
        camera_name=camera_name,
        zones_data=camera_data.get("zones") or [],
        seen_zone_keys=seen_zone_keys,
    )

    if warn_on_empty_zones and not zones:
        LOGGER.warning("Camera '%s' không có zone hợp lệ.", camera_name)

    seen_camera_ids.add(camera_id)
    return Camera(
        id=camera_id,
        name=camera_name,
        source=source,
        zones=zones,
        enabled=enabled,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _parse_zones(
    *,
    camera_id: str,
    camera_name: str,
    zones_data: Any,
    seen_zone_keys: Set[str],
) -> List[Zone]:
    if not isinstance(zones_data, list):
        LOGGER.warning("Camera '%s' có field zones không phải list.", camera_id)
        return []

    zones: List[Zone] = []
    for zone_data in zones_data:
        zone = _parse_zone(
            camera_id=camera_id,
            camera_name=camera_name,
            zone_data=zone_data,
            seen_zone_keys=seen_zone_keys,
        )
        if zone is not None:
            zones.append(zone)
    return zones


# ─────────────────────────────────────────────────────────────────────────────
def _parse_zone(
    *,
    camera_id: str,
    camera_name: str,
    zone_data: Any,
    seen_zone_keys: Set[str],
) -> Optional[Zone]:
    if not isinstance(zone_data, Mapping):
        LOGGER.warning("Bỏ qua zone không phải dict trong camera '%s'.", camera_id)
        return None

    zone_name = str(zone_data.get("name") or "").strip()
    zone_id   = str(zone_data.get("id")   or zone_name).strip()
    points    = zone_data.get("points") or []

    if not zone_name or not points:
        LOGGER.warning("Bỏ qua zone thiếu name hoặc points trong camera '%s'.", camera_id)
        return None

    zone_key = f"{camera_id}.{zone_name}"
    if zone_key in seen_zone_keys:
        LOGGER.warning("Bỏ qua zone trùng key '%s'.", zone_key)
        return None

    if not _is_valid_polygon(points):
        LOGGER.warning("Bỏ qua zone '%s' vì points không hợp lệ.", zone_key)
        return None

    seen_zone_keys.add(zone_key)
    return Zone(
        id=zone_id,
        camera_id=camera_id,
        camera_name=camera_name,
        name=zone_name,
        pts=np.asarray(points, dtype=np.int32),
        goal_pose=dict(zone_data.get("goal_pose") or {}),
    )


# ─────────────────────────────────────────────────────────────────────────────
def _is_valid_polygon(points: Any) -> bool:
    if not isinstance(points, list) or len(points) < 3:
        return False
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            return False
        try:
            if not all(np.isfinite(float(v)) for v in point):
                return False
        except (TypeError, ValueError):
            return False
    return True
