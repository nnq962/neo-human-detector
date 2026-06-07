"""
Loader camera từ dict config.

Module này là nguồn chính để parse camera runtime từ config. Khác biệt chính:
- Trả list rỗng thay vì None để code gọi dễ xử lý hơn.
- Giữ đầy đủ thông tin stream/protocol/enabled trên Camera model.
- Validate zone/camera theo từng bước nhỏ, dễ test riêng.
"""

from collections.abc import Mapping
from typing import Any, List, Optional, Set

import numpy as np

from src.camera.models import Camera, CameraStreamConfig
from src.zones.models import Zone
from utils import LOGGER


# ─────────────────────────────────────────────────────────────────────────────
def load_cameras_from_config(
    config: Mapping[str, Any],
    *,
    enabled_only: bool = True,
    parse_zones: bool = True,
    warn_on_empty_zones: bool = True,
) -> List[Camera]:
    """
    Parse danh sách camera từ config root.

    Args:
        config: Dict config đã load từ YAML.
        enabled_only: True thì bỏ qua camera `enabled: false`.
        parse_zones: True thì parse zone polygon, False chỉ load stream camera.
        warn_on_empty_zones: True thì cảnh báo camera không có zone hợp lệ.

    Returns:
        Danh sách Camera hợp lệ. Nếu không có camera hợp lệ thì trả list rỗng.
    """
    cameras_data = config.get("cameras") or []
    if not isinstance(cameras_data, list):
        LOGGER.warning("Config field 'cameras' không phải list, bỏ qua.")
        return []

    cameras: List[Camera] = []
    seen_camera_ids: Set[str] = set()
    seen_zone_keys: Set[str] = set()

    for camera_data in cameras_data:
        camera = parse_camera_config(
            camera_data,
            seen_camera_ids=seen_camera_ids,
            seen_zone_keys=seen_zone_keys,
            enabled_only=enabled_only,
            parse_zones=parse_zones,
            warn_on_empty_zones=warn_on_empty_zones,
        )
        if camera is not None:
            cameras.append(camera)

    return cameras


# ─────────────────────────────────────────────────────────────────────────────
def parse_camera_config(
    camera_data: Any,
    *,
    seen_camera_ids: Set[str],
    seen_zone_keys: Set[str],
    enabled_only: bool = True,
    parse_zones: bool = True,
    warn_on_empty_zones: bool = True,
) -> Optional[Camera]:
    """Parse một camera config thành Camera runtime."""
    if not isinstance(camera_data, Mapping):
        LOGGER.warning("Bỏ qua camera config không phải dict: %s", camera_data)
        return None

    enabled = bool(camera_data.get("enabled", True))
    if enabled_only and not enabled:
        return None

    camera_id = str(camera_data.get("id") or "").strip()
    source = str(camera_data.get("source") or "").strip()
    camera_name = str(camera_data.get("name") or camera_id).strip()

    if not camera_id or not source:
        LOGGER.warning("Bỏ qua camera thiếu id hoặc source: %s", camera_data)
        return None

    if camera_id in seen_camera_ids:
        LOGGER.warning("Bỏ qua camera trùng id '%s'.", camera_id)
        return None

    zones = []
    if parse_zones:
        zones = parse_camera_zones(
            camera_id=camera_id,
            camera_name=camera_name,
            zones_data=camera_data.get("zones") or [],
            seen_zone_keys=seen_zone_keys,
        )

    if parse_zones and warn_on_empty_zones and not zones:
        LOGGER.warning("Camera '%s' không có zone hợp lệ.", camera_name)

    seen_camera_ids.add(camera_id)
    return Camera(
        id=camera_id,
        name=camera_name,
        stream=CameraStreamConfig(
            source=source,
            source_protocol=_normalize_source_protocol(camera_data.get("source_protocol")),
            source_on_demand=bool(camera_data.get("source_on_demand", True)),
        ),
        zones=zones,
        enabled=enabled,
    )


# ─────────────────────────────────────────────────────────────────────────────
def parse_camera_zones(
    *,
    camera_id: str,
    camera_name: str,
    zones_data: Any,
    seen_zone_keys: Set[str],
) -> List[Zone]:
    """Parse toàn bộ zone thuộc một camera."""
    if not isinstance(zones_data, list):
        LOGGER.warning("Camera '%s' có field zones không phải list, bỏ qua zones.", camera_id)
        return []

    zones: List[Zone] = []
    for zone_data in zones_data:
        zone = parse_zone_config(
            camera_id=camera_id,
            camera_name=camera_name,
            zone_data=zone_data,
            seen_zone_keys=seen_zone_keys,
        )
        if zone is not None:
            zones.append(zone)

    return zones


# ─────────────────────────────────────────────────────────────────────────────
def parse_zone_config(
    *,
    camera_id: str,
    camera_name: str,
    zone_data: Any,
    seen_zone_keys: Set[str],
) -> Optional[Zone]:
    """Parse một zone config thành Zone runtime."""
    if not isinstance(zone_data, Mapping):
        LOGGER.warning("Bỏ qua zone không phải dict trong camera '%s': %s", camera_id, zone_data)
        return None

    zone_name = str(zone_data.get("name") or "").strip()
    points = zone_data.get("points") or []

    if not zone_name or not points:
        LOGGER.warning("Bỏ qua zone thiếu name hoặc points trong camera '%s': %s", camera_id, zone_data)
        return None

    zone_key = f"{camera_id}.{zone_name}"
    if zone_key in seen_zone_keys:
        LOGGER.warning("Bỏ qua zone trùng key '%s'.", zone_key)
        return None

    if not _is_valid_polygon_points(points):
        LOGGER.warning("Bỏ qua zone '%s' vì points không hợp lệ.", zone_key)
        return None

    seen_zone_keys.add(zone_key)
    return Zone(
        camera_id=camera_id,
        camera_name=camera_name,
        name=zone_name,
        pts=np.asarray(points, dtype=np.int32),
        goal_pose=dict(zone_data.get("goal_pose") or {}),
    )


# ─────────────────────────────────────────────────────────────────────────────
def flatten_camera_zones(cameras: List[Camera]) -> List[Zone]:
    """Gom tất cả zone từ nhiều camera thành một list phẳng."""
    zones: List[Zone] = []
    for camera in cameras:
        zones.extend(camera.zones)

    return zones


# ─────────────────────────────────────────────────────────────────────────────
def _normalize_source_protocol(value: Any) -> str:
    """Chuẩn hóa source protocol về nhóm MediaMTX/RTSP đang hỗ trợ."""
    protocol = str(value or "tcp").strip().lower()
    if protocol in {"tcp", "udp", "multicast"}:
        return protocol

    LOGGER.warning("source_protocol '%s' không hỗ trợ, fallback về 'tcp'.", value)
    return "tcp"


# ─────────────────────────────────────────────────────────────────────────────
def _is_valid_polygon_points(points: Any) -> bool:
    """Kiểm tra points có thể tạo thành polygon tối thiểu 3 điểm hay không."""
    if not isinstance(points, list) or len(points) < 3:
        return False

    for point in points:
        if not isinstance(point, list) and not isinstance(point, tuple):
            return False
        if len(point) != 2:
            return False
        if not all(_is_number(value) for value in point):
            return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
def _is_number(value: Any) -> bool:
    """Kiểm tra value là số int/float hữu hạn."""
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False
