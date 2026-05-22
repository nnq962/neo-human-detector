from typing import List

from fastapi import APIRouter, HTTPException, Request, Response, status

from api.models.camera import Camera, CameraCreate, CameraUpdate
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


def _handle_camera_error(error: Exception) -> HTTPException:
    if isinstance(error, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(error))

    if isinstance(error, KeyError):
        return HTTPException(status_code=404, detail=str(error))

    if isinstance(error, ValueError):
        return HTTPException(status_code=409, detail=str(error))

    return HTTPException(status_code=500, detail=str(error))


@router.get("", response_model=List[Camera])
def list_cameras(request: Request):
    try:
        cameras = camera_service.list_cameras()

        return [_with_request_webrtc_address(camera, request) for camera in cameras]
    except Exception as error:
        raise _handle_camera_error(error)


@router.get("/{camera_id}", response_model=Camera)
def get_camera(camera_id: str, request: Request):
    try:
        return _with_request_webrtc_address(camera_service.get_camera(camera_id), request)
    except Exception as error:
        raise _handle_camera_error(error)


@router.post("", response_model=Camera, status_code=status.HTTP_201_CREATED)
def create_camera(camera: CameraCreate, request: Request):
    try:
        return _with_request_webrtc_address(camera_service.create_camera(camera), request)
    except Exception as error:
        raise _handle_camera_error(error)


@router.put("/{camera_id}", response_model=Camera)
def replace_camera(camera_id: str, camera: CameraCreate, request: Request):
    try:
        return _with_request_webrtc_address(
            camera_service.replace_camera(camera_id, camera),
            request,
        )
    except Exception as error:
        raise _handle_camera_error(error)


@router.patch("/{camera_id}", response_model=Camera)
def update_camera(camera_id: str, camera: CameraUpdate, request: Request):
    try:
        return _with_request_webrtc_address(
            camera_service.update_camera(camera_id, camera),
            request,
        )
    except Exception as error:
        raise _handle_camera_error(error)


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_camera(camera_id: str):
    try:
        camera_service.delete_camera(camera_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as error:
        raise _handle_camera_error(error)
