import secrets
import string
from typing import List

from api.models.camera import CameraCreate, CameraUpdate
from api.services import config_store
from api.services import mediamtx as mediamtx_service

CAMERA_ID_LENGTH = 5
CAMERA_ID_ALPHABET = string.ascii_lowercase + string.digits
ZONE_ID_LENGTH = 5
ZONE_ID_ALPHABET = string.ascii_lowercase + string.digits


def _model_dump(model, **kwargs) -> dict:
    return model.model_dump(**kwargs)


def _get_config() -> dict:
    return config_store.get_config_data()


def _get_cameras(config: dict) -> List[dict]:
    cameras = config.setdefault("cameras", [])

    if cameras is None:
        cameras = []
        config["cameras"] = cameras

    return cameras


def _find_camera_index(cameras: List[dict], camera_id: str) -> int:
    for index, camera in enumerate(cameras):
        if camera.get("id") == camera_id:
            return index

    raise KeyError(f'Camera "{camera_id}" not found.')


def _ensure_unique_camera_id(cameras: List[dict], camera_id: str, ignore_index: int = -1) -> None:
    for index, camera in enumerate(cameras):
        if index != ignore_index and camera.get("id") == camera_id:
            raise ValueError(f'Camera "{camera_id}" already exists.')


def _generate_camera_id(cameras: List[dict]) -> str:
    existing_ids = {camera.get("id") for camera in cameras}

    while True:
        camera_id = "".join(
            secrets.choice(CAMERA_ID_ALPHABET) for _ in range(CAMERA_ID_LENGTH)
        )

        if camera_id not in existing_ids:
            return camera_id


def _generate_zone_id(existing_ids: set[str]) -> str:
    while True:
        zone_id = "".join(
            secrets.choice(ZONE_ID_ALPHABET) for _ in range(ZONE_ID_LENGTH)
        )

        if zone_id not in existing_ids:
            existing_ids.add(zone_id)
            return zone_id


def _collect_zone_ids(cameras: List[dict], ignore_camera_index: int = -1) -> set[str]:
    zone_ids: set[str] = set()

    for index, camera in enumerate(cameras):
        if index == ignore_camera_index:
            continue

        for zone in camera.get("zones") or []:
            zone_id = str(zone.get("id") or "").strip()
            if zone_id:
                zone_ids.add(zone_id)

    return zone_ids


def _ensure_zone_ids(camera: dict, cameras: List[dict], ignore_camera_index: int = -1) -> None:
    existing_ids = _collect_zone_ids(cameras, ignore_camera_index=ignore_camera_index)

    for zone in camera.get("zones") or []:
        zone_id = str(zone.get("id") or "").strip()
        if zone_id and zone_id not in existing_ids:
            zone["id"] = zone_id
            existing_ids.add(zone_id)
            continue

        zone["id"] = _generate_zone_id(existing_ids)


def _strip_runtime_fields(camera: dict) -> dict:
    return {
        key: value
        for key, value in camera.items()
        if key not in {"webrtc_address"}
    }


def _with_runtime_fields(camera: dict) -> dict:
    return mediamtx_service.attach_webrtc_address(camera)


def _stream_config_changed(current_camera: dict, next_camera: dict) -> bool:
    current_stream_config = {
        "enabled": current_camera.get("enabled", True),
        **mediamtx_service.build_path_payload(current_camera),
    }
    next_stream_config = {
        "enabled": next_camera.get("enabled", True),
        **mediamtx_service.build_path_payload(next_camera),
    }

    return current_stream_config != next_stream_config


def list_cameras() -> List[dict]:
    config = _get_config()

    return [_with_runtime_fields(camera) for camera in _get_cameras(config)]


def get_camera(camera_id: str) -> dict:
    config = _get_config()
    cameras = _get_cameras(config)
    index = _find_camera_index(cameras, camera_id)

    return _with_runtime_fields(cameras[index])


def create_camera(camera: CameraCreate) -> dict:
    camera_data = _model_dump(camera)

    def mutate(config: dict) -> dict:
        cameras = _get_cameras(config)
        next_camera = dict(camera_data)

        next_camera["id"] = _generate_camera_id(cameras)
        _ensure_unique_camera_id(cameras, next_camera["id"])
        _ensure_zone_ids(next_camera, cameras)

        cameras.append(next_camera)
        return next_camera

    created_camera = config_store.update_config_data(mutate)
    mediamtx_service.upsert_camera_path(created_camera)
    return _with_runtime_fields(created_camera)


def replace_camera(camera_id: str, camera: CameraCreate) -> dict:
    camera_data = _model_dump(camera)

    def mutate(config: dict) -> dict:
        cameras = _get_cameras(config)
        index = _find_camera_index(cameras, camera_id)
        current_camera = _strip_runtime_fields(cameras[index])
        next_camera = dict(camera_data)

        next_camera["id"] = camera_id
        _ensure_unique_camera_id(cameras, next_camera["id"], ignore_index=index)
        _ensure_zone_ids(next_camera, cameras, ignore_camera_index=index)

        sync_required = _stream_config_changed(current_camera, next_camera)

        cameras[index] = next_camera
        return {
            "camera": next_camera,
            "sync_required": sync_required,
        }

    result = config_store.update_config_data(mutate)
    replaced_camera = result["camera"]
    if result["sync_required"]:
        mediamtx_service.upsert_camera_path(replaced_camera)

    return _with_runtime_fields(replaced_camera)


def update_camera(camera_id: str, patch: CameraUpdate) -> dict:
    patch_data = _model_dump(patch, exclude_none=True, exclude_unset=True)

    if not patch_data:
        return get_camera(camera_id)

    def mutate(config: dict) -> dict:
        cameras = _get_cameras(config)
        index = _find_camera_index(cameras, camera_id)

        current_camera = _strip_runtime_fields(cameras[index])
        next_camera = {**current_camera, **patch_data}
        if "stream" in patch_data:
            next_camera["stream"] = {
                **(current_camera.get("stream") or {}),
                **patch_data["stream"],
            }
        _ensure_unique_camera_id(cameras, next_camera["id"], ignore_index=index)
        _ensure_zone_ids(next_camera, cameras, ignore_camera_index=index)

        sync_required = _stream_config_changed(current_camera, next_camera)

        cameras[index] = next_camera
        return {
            "camera": next_camera,
            "sync_required": sync_required,
        }

    result = config_store.update_config_data(mutate)
    updated_camera = result["camera"]
    if result["sync_required"]:
        mediamtx_service.upsert_camera_path(updated_camera)

    return _with_runtime_fields(updated_camera)


def delete_camera(camera_id: str) -> dict:
    def mutate(config: dict) -> dict:
        cameras = _get_cameras(config)
        index = _find_camera_index(cameras, camera_id)
        camera = cameras.pop(index)
        return camera

    deleted_camera = config_store.update_config_data(mutate)
    mediamtx_service.delete_camera_path(camera_id, ignore_missing=True)
    return _with_runtime_fields(deleted_camera)
