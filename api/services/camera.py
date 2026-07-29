from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from typing import List

from api.models.camera import (
    CalibrationApplyRequest,
    CalibrationPreviewRequest,
    CameraCreate,
    CameraUpdate,
)
from api.services import config_store
from api.services import mediamtx as mediamtx_service
from src.calibration import calculate_homography

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


# ─────────────────────────────────────────────────────────────────────────────
def _normalize_zone_fields(camera: dict) -> None:
    """Loại bỏ goal pose cũ và chuẩn hóa field điểm phục vụ của các zone."""
    for zone in camera.get("zones") or []:
        zone.pop("goal_pose", None)
        zone.setdefault("service_point", None)


# ─────────────────────────────────────────────────────────────────────────────
def _validate_new_zone_service_points(
    camera: dict,
    current_camera: dict | None = None,
) -> None:
    """Từ chối zone mới chưa có điểm phục vụ pixel."""
    current_zone_ids = {
        str(zone.get("id"))
        for zone in (current_camera or {}).get("zones") or []
        if zone.get("id")
    }
    for zone in camera.get("zones") or []:
        zone_id = str(zone.get("id") or "")
        if zone_id and zone_id in current_zone_ids:
            continue
        if zone.get("service_point") is None:
            raise ValueError(
                f'Zone mới "{zone.get("name") or "không tên"}" '
                "phải có service_point trước khi lưu."
            )


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


# ─────────────────────────────────────────────────────────────────────────────
def preview_camera_calibration(
    camera_id: str,
    request: CalibrationPreviewRequest,
) -> dict:
    """Tính thử Homography cho camera mà không thay đổi cấu hình."""
    get_camera(camera_id)

    width = request.image_size.width
    height = request.image_size.height
    for point in request.points:
        if not 0 <= point.pixel.u < width or not 0 <= point.pixel.v < height:
            raise ValueError(
                f'Pixel của point "{point.id}" nằm ngoài độ phân giải video.'
            )

    result = calculate_homography(
        [(point.pixel.u, point.pixel.v) for point in request.points],
        [(point.world.x, point.world.y) for point in request.points],
        point_ids=[point.id for point in request.points],
        ransac_threshold_m=request.ransac_threshold_m,
    )
    return {
        "camera_id": camera_id,
        "image_size": request.image_size.model_dump(),
        **result,
    }


# ─────────────────────────────────────────────────────────────────────────────
def get_camera_calibration(camera_id: str) -> dict | None:
    """Lấy calibration đã lưu của camera hoặc ``None`` nếu chưa có."""
    config = _get_config()
    cameras = _get_cameras(config)
    index = _find_camera_index(cameras, camera_id)
    calibration = cameras[index].get("calibration")
    if calibration is None:
        return None
    return {"camera_id": camera_id, **calibration}


# ─────────────────────────────────────────────────────────────────────────────
def apply_camera_calibration(
    camera_id: str,
    request: CalibrationApplyRequest,
) -> dict:
    """Tính lại và lưu calibration vào đúng camera trong cấu hình."""
    preview = preview_camera_calibration(camera_id, request)
    rating = preview["quality"]["rating"]

    if rating == "RECALIBRATE":
        raise ValueError(
            "Chất lượng calibration quá thấp; vui lòng đo lại các điểm."
        )
    if rating in {"CHECK", "LIMITED"} and not request.accept_warning:
        raise ValueError(
            "Calibration cần xác nhận cảnh báo trước khi áp dụng."
        )

    results_by_id = {point["id"]: point for point in preview["points"]}
    calibration = {
        "image_size": request.image_size.model_dump(),
        "direction": preview["direction"],
        "method": preview["method"],
        "ransac_threshold_m": preview["ransac_threshold_m"],
        "homography": preview["homography"],
        "quality": preview["quality"],
        "points": [
            {
                "id": point.id,
                "pixel": [point.pixel.u, point.pixel.v],
                "world": [point.world.x, point.world.y],
                "robot_id": point.robot_id,
                "valid": results_by_id[point.id]["valid"],
                "predicted_world": [
                    results_by_id[point.id]["predicted_world"]["x"],
                    results_by_id[point.id]["predicted_world"]["y"],
                ],
                "error_m": results_by_id[point.id]["error_m"],
                "validation_error_m": results_by_id[point.id][
                    "validation_error_m"
                ],
            }
            for point in request.points
        ],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # ─────────────────────────────────────────────────────────────────────────────
    def mutate(config: dict) -> None:
        """Gắn calibration mới vào camera trong config đang được khóa."""
        cameras = _get_cameras(config)
        index = _find_camera_index(cameras, camera_id)
        cameras[index]["calibration"] = calibration

    config_store.update_config_data(mutate)
    return {"camera_id": camera_id, **calibration}


# ─────────────────────────────────────────────────────────────────────────────
def delete_camera_calibration(camera_id: str) -> dict | None:
    """Xóa calibration của camera mà không thay đổi các cấu hình khác."""
    # ─────────────────────────────────────────────────────────────────────────────
    def mutate(config: dict) -> dict | None:
        """Gỡ và trả calibration trong config đang được khóa."""
        cameras = _get_cameras(config)
        index = _find_camera_index(cameras, camera_id)
        return cameras[index].pop("calibration", None)

    deleted = config_store.update_config_data(mutate)
    if deleted is None:
        return None
    return {"camera_id": camera_id, **deleted}


def create_camera(camera: CameraCreate) -> dict:
    camera_data = _model_dump(camera)

    def mutate(config: dict) -> dict:
        cameras = _get_cameras(config)
        next_camera = dict(camera_data)

        next_camera["id"] = _generate_camera_id(cameras)
        _normalize_zone_fields(next_camera)
        _validate_new_zone_service_points(next_camera)
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
        if current_camera.get("calibration") is not None:
            next_camera["calibration"] = current_camera["calibration"]
        _normalize_zone_fields(next_camera)
        _validate_new_zone_service_points(next_camera, current_camera)
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
        _normalize_zone_fields(next_camera)
        _validate_new_zone_service_points(next_camera, current_camera)
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
