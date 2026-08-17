"""
Camera config model và loader từ YAML.

Module này chịu trách nhiệm parse camera config và dựng Zone tương ứng.
Việc đọc stream (RTSP) được xử lý ở tầng khác bởi MediaSources.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

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
    calibration_image_size: Optional[tuple[int, int]] = None

    # ─────────────────────────────────────────────────────────────────────────
    @property
    def zone_count(self) -> int:
        """Trả số zone runtime thuộc camera."""
        return len(self.zones)

    # ─────────────────────────────────────────────────────────────────────────
    def is_ready_for_detection(self) -> bool:
        """Kiểm tra camera đang bật và có đủ ID cùng nguồn stream."""
        return self.enabled and bool(self.id) and bool(self.source)


# ─────────────────────────────────────────────────────────────────────────────
def load_cameras_from_config(
    config: Mapping[str, Any],
    *,
    camera_ids: Optional[Iterable[str]] = None,
    enabled_only: bool = True,
    warn_on_empty_zones: bool = True,
) -> List[Camera]:
    """Parse danh sách camera từ config root."""
    cameras_data = config.get("cameras") or []
    if not isinstance(cameras_data, list):
        LOGGER.warning("Config field 'cameras' không phải list, bỏ qua.")
        return []

    if camera_ids is not None:
        camera_by_id = {
            str(camera.get("id")): camera
            for camera in cameras_data
            if isinstance(camera, Mapping) and camera.get("id")
        }
        cameras_data = [
            camera_by_id[camera_id]
            for camera_id in camera_ids
            if camera_id in camera_by_id
        ]

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
    """Parse một camera config, trả ``None`` khi dữ liệu không hợp lệ."""
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

    calibration_data = camera_data.get("calibration")
    if not isinstance(calibration_data, Mapping):
        calibration_data = {}
    calibration_image_size = _parse_calibration_image_size(
        calibration_data.get("image_size"),
    )
    homography = calibration_data.get("homography")

    zones = _parse_zones(
        camera_id=camera_id,
        camera_name=camera_name,
        zones_data=camera_data.get("zones") or [],
        homography=homography,
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
        calibration_image_size=calibration_image_size,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _parse_zones(
    *,
    camera_id: str,
    camera_name: str,
    zones_data: Any,
    homography: Any,
    seen_zone_keys: Set[str],
) -> List[Zone]:
    """Parse danh sách zone hợp lệ thuộc một camera."""
    if not isinstance(zones_data, list):
        LOGGER.warning("Camera '%s' có field zones không phải list.", camera_id)
        return []

    zones: List[Zone] = []
    for zone_data in zones_data:
        zone = _parse_zone(
            camera_id=camera_id,
            camera_name=camera_name,
            zone_data=zone_data,
            homography=homography,
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
    homography: Any,
    seen_zone_keys: Set[str],
) -> Optional[Zone]:
    """Parse một zone và dựng goal pose từ calibration nếu có."""
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

    service_point = _parse_service_point(zone_data.get("service_point"))
    goal_pose = _build_goal_pose(service_point, points, homography)
    if not goal_pose:
        goal_pose = dict(zone_data.get("goal_pose") or {})

    seen_zone_keys.add(zone_key)
    return Zone(
        id=zone_id,
        camera_id=camera_id,
        camera_name=camera_name,
        name=zone_name,
        pts=np.asarray(points, dtype=np.int32),
        goal_pose=goal_pose,
        service_point=service_point,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _parse_service_point(value: Any) -> Optional[tuple[float, float]]:
    """Đọc điểm phục vụ pixel và trả về cặp tọa độ hợp lệ."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None

    try:
        point = (float(value[0]), float(value[1]))
    except (TypeError, ValueError):
        return None
    if not all(np.isfinite(coordinate) for coordinate in point):
        return None
    return point


# ─────────────────────────────────────────────────────────────────────────────
def _parse_calibration_image_size(value: Any) -> Optional[tuple[int, int]]:
    """Đọc độ phân giải dùng để calibration dưới dạng ``(width, height)``."""
    if not isinstance(value, Mapping):
        return None

    try:
        width = int(value["width"])
        height = int(value["height"])
    except (KeyError, TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


# ─────────────────────────────────────────────────────────────────────────────
def _project_pixel_point(
    point: tuple[float, float],
    matrix: np.ndarray,
) -> Optional[tuple[float, float]]:
    """Chiếu một điểm pixel sang hệ tọa độ robot bằng homography."""
    projected = matrix @ np.asarray(
        [point[0], point[1], 1.0],
        dtype=np.float64,
    )
    denominator = float(projected[2])
    if not np.isfinite(denominator) or abs(denominator) < 1e-9:
        return None

    x = float(projected[0] / denominator)
    y = float(projected[1] / denominator)
    if not np.isfinite(x) or not np.isfinite(y):
        return None
    return x, y


# ─────────────────────────────────────────────────────────────────────────────
def _polygon_centroid(
    points: list[tuple[float, float]],
) -> Optional[tuple[float, float]]:
    """Tính tâm hình học có trọng số diện tích của polygon tọa độ robot."""
    if len(points) < 3:
        return None

    polygon = np.asarray(points, dtype=np.float64)
    next_polygon = np.roll(polygon, -1, axis=0)
    cross_products = (
        polygon[:, 0] * next_polygon[:, 1]
        - next_polygon[:, 0] * polygon[:, 1]
    )
    twice_area = float(np.sum(cross_products))
    if not np.isfinite(twice_area) or abs(twice_area) < 1e-9:
        center = np.mean(polygon, axis=0)
        if not np.isfinite(center).all():
            return None
        return float(center[0]), float(center[1])

    center_x = float(
        np.sum((polygon[:, 0] + next_polygon[:, 0]) * cross_products)
        / (3.0 * twice_area)
    )
    center_y = float(
        np.sum((polygon[:, 1] + next_polygon[:, 1]) * cross_products)
        / (3.0 * twice_area)
    )
    if not np.isfinite(center_x) or not np.isfinite(center_y):
        return None
    return center_x, center_y


# ─────────────────────────────────────────────────────────────────────────────
def _calculate_service_theta(
    zone_center: tuple[float, float],
    goal_point: tuple[float, float],
) -> float:
    """Tính theta để mặt robot hướng ra ngoài và mông quay về tâm zone."""
    delta_x = goal_point[0] - zone_center[0]
    delta_y = goal_point[1] - zone_center[1]
    if math.hypot(delta_x, delta_y) < 1e-9:
        return 0.0
    return math.atan2(delta_y, delta_x)


# ─────────────────────────────────────────────────────────────────────────────
def _build_goal_pose(
    service_point: Optional[tuple[float, float]],
    zone_points: Any,
    homography: Any,
) -> Dict[str, float]:
    """Tạo goal pose runtime từ điểm phục vụ, polygon zone và homography."""
    if service_point is None:
        return {}

    try:
        matrix = np.asarray(homography, dtype=np.float64)
    except (TypeError, ValueError):
        return {}
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        return {}

    goal_point = _project_pixel_point(service_point, matrix)
    if goal_point is None:
        return {}

    projected_zone_points = [
        projected
        for point in zone_points
        if (projected := _project_pixel_point(
            (float(point[0]), float(point[1])),
            matrix,
        )) is not None
    ]
    zone_center = _polygon_centroid(projected_zone_points)
    theta = (
        _calculate_service_theta(zone_center, goal_point)
        if zone_center is not None
        else 0.0
    )
    return {"x": goal_point[0], "y": goal_point[1], "theta": theta}


# ─────────────────────────────────────────────────────────────────────────────
def _is_valid_polygon(points: Any) -> bool:
    """Kiểm tra polygon có đủ ba điểm phân biệt và diện tích khác không."""
    if not isinstance(points, list) or len(points) < 3:
        return False
    normalized_points: list[tuple[float, float]] = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            return False
        try:
            normalized_point = tuple(float(value) for value in point)
            if not all(np.isfinite(value) for value in normalized_point):
                return False
            normalized_points.append(normalized_point)
        except (TypeError, ValueError):
            return False
    if len(set(normalized_points)) < 3:
        return False
    polygon = np.asarray(normalized_points, dtype=np.float64)
    shifted = np.roll(polygon, -1, axis=0)
    twice_area = np.sum(
        polygon[:, 0] * shifted[:, 1]
        - shifted[:, 0] * polygon[:, 1]
    )
    return bool(abs(twice_area) > 0)
