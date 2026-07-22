from fastapi import APIRouter, Request, status

from api.models.camera import (
    CalibrationApplyRequest,
    CalibrationPreviewRequest,
    CameraCreate,
    CameraUpdate,
)
from api.models.response import ApiResponse
from api.routes.responses import error_from_exception, ok
from api.services import mediamtx as mediamtx_service
from api.services import camera as camera_service


router = APIRouter()


def _webrtc_base_url_from_request(request: Request) -> str:
    scheme = "https" if request.url.scheme == "https" else "http"

    return mediamtx_service.get_webrtc_base_url(request.url.hostname, scheme)


def _with_request_webrtc_address(camera: dict, request: Request) -> dict:
    return mediamtx_service.attach_webrtc_address(
        camera,
        _webrtc_base_url_from_request(request),
    )


@router.get("", response_model=ApiResponse)
def list_cameras(request: Request):
    try:
        cameras = camera_service.list_cameras()
        data = [_with_request_webrtc_address(camera, request) for camera in cameras]

        return ok("Cameras loaded successfully.", data)
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)


@router.get("/{camera_id}", response_model=ApiResponse)
def get_camera(camera_id: str, request: Request):
    try:
        data = _with_request_webrtc_address(camera_service.get_camera(camera_id), request)
        return ok("Camera loaded successfully.", data)
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)


# ─────────────────────────────────────────────────────────────────────────────
@router.post("/{camera_id}/calibration/preview", response_model=ApiResponse)
def preview_camera_calibration(
    camera_id: str,
    calibration: CalibrationPreviewRequest,
):
    """Tính thử Homography cho camera mà không lưu vào cấu hình."""
    try:
        data = camera_service.preview_camera_calibration(camera_id, calibration)
        return ok("Camera calibration preview calculated successfully.", data)
    except Exception as error:
        return error_from_exception(error)


# ─────────────────────────────────────────────────────────────────────────────
@router.get("/{camera_id}/calibration", response_model=ApiResponse)
def get_camera_calibration(camera_id: str):
    """Lấy calibration đã áp dụng của camera."""
    try:
        data = camera_service.get_camera_calibration(camera_id)
        return ok("Camera calibration loaded successfully.", data)
    except Exception as error:
        return error_from_exception(error)


# ─────────────────────────────────────────────────────────────────────────────
@router.put("/{camera_id}/calibration", response_model=ApiResponse)
def apply_camera_calibration(
    camera_id: str,
    calibration: CalibrationApplyRequest,
):
    """Tính lại và áp dụng calibration cho camera."""
    try:
        data = camera_service.apply_camera_calibration(camera_id, calibration)
        return ok("Camera calibration applied successfully.", data)
    except Exception as error:
        return error_from_exception(error)


# ─────────────────────────────────────────────────────────────────────────────
@router.delete("/{camera_id}/calibration", response_model=ApiResponse)
def delete_camera_calibration(camera_id: str):
    """Xóa calibration đã lưu của camera."""
    try:
        data = camera_service.delete_camera_calibration(camera_id)
        return ok("Camera calibration deleted successfully.", data)
    except Exception as error:
        return error_from_exception(error)


@router.post("", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
def create_camera(camera: CameraCreate, request: Request):
    try:
        data = _with_request_webrtc_address(camera_service.create_camera(camera), request)
        return ok("Camera created successfully.", data)
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)


@router.put("/{camera_id}", response_model=ApiResponse)
def replace_camera(camera_id: str, camera: CameraCreate, request: Request):
    try:
        data = _with_request_webrtc_address(
            camera_service.replace_camera(camera_id, camera),
            request,
        )
        return ok("Camera replaced successfully.", data)
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)


@router.patch("/{camera_id}", response_model=ApiResponse)
def update_camera(camera_id: str, camera: CameraUpdate, request: Request):
    try:
        data = _with_request_webrtc_address(
            camera_service.update_camera(camera_id, camera),
            request,
        )
        return ok("Camera updated successfully.", data)
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)


@router.delete("/{camera_id}", response_model=ApiResponse)
def delete_camera(camera_id: str):
    try:
        data = camera_service.delete_camera(camera_id)
        return ok("Camera deleted successfully.", data)
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)
