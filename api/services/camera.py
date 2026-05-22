import secrets
import string
from typing import List

from api.models.camera import CameraCreate, CameraUpdate
from api.services import config_store
from api.services import mediamtx as mediamtx_service

CAMERA_ID_LENGTH = 5
CAMERA_ID_ALPHABET = string.ascii_lowercase + string.digits


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
    config = _get_config()
    cameras = _get_cameras(config)
    camera_data = _model_dump(camera)

    camera_data["id"] = _generate_camera_id(cameras)
    _ensure_unique_camera_id(cameras, camera_data["id"])

    mediamtx_service.upsert_camera_path(camera_data)
    cameras.append(camera_data)
    config_store.save_config_data(config)

    return _with_runtime_fields(camera_data)


def replace_camera(camera_id: str, camera: CameraCreate) -> dict:
    config = _get_config()
    cameras = _get_cameras(config)
    index = _find_camera_index(cameras, camera_id)
    current_camera = _strip_runtime_fields(cameras[index])
    camera_data = _model_dump(camera)

    camera_data["id"] = camera_id
    _ensure_unique_camera_id(cameras, camera_data["id"], ignore_index=index)

    if _stream_config_changed(current_camera, camera_data):
        mediamtx_service.upsert_camera_path(camera_data)

    cameras[index] = camera_data
    config_store.save_config_data(config)

    return _with_runtime_fields(camera_data)


def update_camera(camera_id: str, patch: CameraUpdate) -> dict:
    config = _get_config()
    cameras = _get_cameras(config)
    index = _find_camera_index(cameras, camera_id)
    patch_data = _model_dump(patch, exclude_none=True, exclude_unset=True)

    if not patch_data:
        return _with_runtime_fields(cameras[index])

    current_camera = _strip_runtime_fields(cameras[index])
    next_camera = {
        **current_camera,
        **patch_data,
    }
    _ensure_unique_camera_id(cameras, next_camera["id"], ignore_index=index)

    if _stream_config_changed(current_camera, next_camera):
        mediamtx_service.upsert_camera_path(next_camera)

    cameras[index] = next_camera
    config_store.save_config_data(config)

    return _with_runtime_fields(next_camera)


def delete_camera(camera_id: str) -> dict:
    config = _get_config()
    cameras = _get_cameras(config)
    index = _find_camera_index(cameras, camera_id)
    camera = cameras.pop(index)

    mediamtx_service.delete_camera_path(camera_id, ignore_missing=True)
    config_store.save_config_data(config)

    return _with_runtime_fields(camera)
