import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.models.response import ApiResponse
from api.routes.responses import error_from_exception, ok
from api.services import mediamtx as mediamtx_service


router = APIRouter()


class CheckCameraRequest(BaseModel):
    source: str
    source_protocol: str = Field("tcp", alias="sourceProtocol")


@router.post("/check-camera", response_model=ApiResponse)
def check_camera(camera: CheckCameraRequest):
    temp_path_name = f"test_cam_{uuid.uuid4().hex[:12]}"

    try:
        mediamtx_service.request_mediamtx(
            f"/config/paths/add/{temp_path_name}",
            method="POST",
            payload={
                "source": camera.source,
                "sourceProtocol": camera.source_protocol,
                "sourceOnDemand": False,
            },
        )

        data = {
            "pathName": temp_path_name,
            "ready": mediamtx_service.wait_for_path_ready(temp_path_name),
        }
        return ok("Camera checked successfully.", data)
    except Exception as error:
        return error_from_exception(error)
    finally:
        try:
            mediamtx_service.request_mediamtx(
                f"/config/paths/delete/{temp_path_name}",
                method="DELETE",
            )
        except HTTPException:
            pass
