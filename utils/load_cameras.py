from typing import List, Optional

import numpy as np

from src.models import Camera, Zone
from .logger import LOGGER


def load_cameras(cfg: dict) -> Optional[List[Camera]]:
    cameras_data = cfg.get("cameras") or []
    if not cameras_data:
        return None

    cameras = []
    seen_camera_ids = set()
    seen_zone_keys = set()

    for camera_dict in cameras_data:
        camera_id = camera_dict.get("id")
        camera_name = camera_dict.get("name", camera_id)
        source = camera_dict.get("source")
        zones_data = camera_dict.get("zones") or []

        if not camera_id or not source:
            LOGGER.warning(f"Bỏ qua camera thiếu id hoặc source: {camera_dict}")
            continue

        if camera_id in seen_camera_ids:
            LOGGER.warning(f"Bỏ qua camera trùng id '{camera_id}'.")
            continue

        zones = []
        for zone_dict in zones_data:
            try:
                name = zone_dict.get("name")
                goal_pose = zone_dict.get("goal_pose", {})
                points = zone_dict.get("points", [])

                if not name or not points:
                    LOGGER.warning(f"Bỏ qua zone thiếu name hoặc points trong camera '{camera_id}': {zone_dict}")
                    continue

                zone_key = f"{camera_id}:{name}"
                if zone_key in seen_zone_keys:
                    LOGGER.warning(f"Bỏ qua zone trùng key '{zone_key}'.")
                    continue

                if len(points) < 3:
                    LOGGER.warning(f"Bỏ qua zone '{zone_key}' vì có ít hơn 3 điểm (chỉ có {len(points)} điểm).")
                    continue

                zone = Zone(
                    camera_id=camera_id,
                    camera_name=camera_name,
                    name=name,
                    pts=np.array(points, dtype=np.int32),
                    goal_pose=goal_pose,
                )
                zones.append(zone)
                seen_zone_keys.add(zone.key)
            except Exception as e:
                LOGGER.warning(f"Lỗi khi parse zone {zone_dict.get('name')} trong camera '{camera_id}': {e}")

        if not zones:
            LOGGER.warning(f"Camera '{camera_id}' không có zone hợp lệ.")

        cameras.append(Camera(
            id=camera_id,
            name=camera_name,
            source=source,
            zones=zones,
        ))
        seen_camera_ids.add(camera_id)

    return cameras if cameras else None


def flatten_camera_zones(cameras: Optional[List[Camera]]) -> List[Zone]:
    zones = []
    for camera in cameras or []:
        zones.extend(camera.zones)
    return zones
