"""API chỉ đọc phục vụ màn hình camera công khai."""

from fastapi import APIRouter, Request

from api.models.response import ApiResponse
from api.routes.responses import error_from_exception, ok
from api.services import camera as camera_service
from api.services import mediamtx as mediamtx_service
from api.services.robot_heartbeat import robot_heartbeat_service


router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
def _webrtc_base_url_from_request(request: Request) -> str:
    """Tạo WHEP base URL khớp hostname mà client đang truy cập."""
    scheme = "https" if request.url.scheme == "https" else "http"
    return mediamtx_service.get_webrtc_base_url(request.url.hostname, scheme)


# ─────────────────────────────────────────────────────────────────────────────
def _serialize_public_camera(camera: dict, request: Request) -> dict:
    """Loại RTSP source và chỉ giữ dữ liệu cần cho trang live."""
    public_camera = {
        "id": camera.get("id"),
        "name": camera.get("name"),
        "enabled": camera.get("enabled", True),
        "zones": camera.get("zones") or [],
    }
    return mediamtx_service.attach_webrtc_address(
        public_camera,
        _webrtc_base_url_from_request(request),
    )


# ─────────────────────────────────────────────────────────────────────────────
@router.get("/cameras", response_model=ApiResponse)
def list_public_cameras(request: Request):
    """Trả các camera đang bật mà không làm lộ RTSP source."""
    try:
        cameras = [
            _serialize_public_camera(camera, request)
            for camera in camera_service.list_cameras()
            if camera.get("enabled", True)
        ]
        return ok("Public cameras loaded successfully.", cameras)
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)


# ─────────────────────────────────────────────────────────────────────────────
@router.get("/cameras/{camera_id}/calibration", response_model=ApiResponse)
def get_public_camera_calibration(camera_id: str):
    """Trả calibration chỉ đọc cho overlay robot trên trang live."""
    try:
        camera = camera_service.get_camera(camera_id)
        if not camera.get("enabled", True):
            raise KeyError(f'Camera "{camera_id}" not found.')
        calibration = camera_service.get_camera_calibration(camera_id)
        return ok("Public camera calibration loaded successfully.", calibration)
    except Exception as error:
        return error_from_exception(error)


# ─────────────────────────────────────────────────────────────────────────────
@router.get("/robots", response_model=ApiResponse)
def get_public_robots():
    """Trả vị trí và trạng thái robot để hiển thị overlay công khai."""
    try:
        return ok(
            "Public robot heartbeat snapshots loaded successfully.",
            robot_heartbeat_service.snapshot(),
        )
    except Exception as error:
        return error_from_exception(error)
