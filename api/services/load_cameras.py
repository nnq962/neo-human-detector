import time
from typing import Any, Dict, Optional

from fastapi import HTTPException

from api.services import mediamtx as mediamtx_service
from utils import LOGGER


def wait_for_mediamtx(max_attempts: int = 60, delay_seconds: float = 1.0) -> None:
    """Wait until the MediaMTX API is ready to accept config updates."""
    last_error: Optional[Exception] = None

    for _ in range(max_attempts):
        try:
            mediamtx_service.request_mediamtx("/config/global/get")
            return
        except HTTPException as e:
            last_error = e

        time.sleep(delay_seconds)

    if last_error:
        raise RuntimeError(f"MediaMTX API is not ready: {last_error.detail}") from last_error

    raise RuntimeError("MediaMTX API is not ready.")


def sync_camera_paths(config: Dict[str, Any]) -> Dict[str, int]:
    """Sync camera entries from app config into MediaMTX path config."""
    result = {
        "synced": 0,
        "failed": 0,
        "skipped": 0,
    }

    for camera in config.get("cameras") or []:
        camera_id = camera.get("id", "<missing-id>")
        stream = camera.get("stream") if isinstance(camera.get("stream"), dict) else {}

        if not camera.get("id") or not stream.get("source"):
            result["skipped"] += 1
            LOGGER.warning(f"Skip MediaMTX camera path with invalid config: {camera_id}")
            continue

        try:
            mediamtx_service.upsert_camera_path(camera)
            result["synced"] += 1
            LOGGER.info(f"Synced MediaMTX camera path: {camera_id}")
        except Exception as e:
            result["failed"] += 1
            LOGGER.error(f"Failed to sync MediaMTX camera path {camera_id}: {e}")

    return result
