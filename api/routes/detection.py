from fastapi import APIRouter

from api.models.detection import DetectionConfig, DetectionConfigUpdate
from api.models.response import ApiResponse
from api.routes.responses import error_from_exception, ok
from api.services import detection as detection_service


router = APIRouter()


@router.get("", response_model=ApiResponse)
def get_detection_config():
    try:
        return ok("Detection config loaded successfully.", detection_service.get_detection_config())
    except Exception as error:
        return error_from_exception(error)


@router.patch("", response_model=ApiResponse)
def update_detection_config(update: DetectionConfigUpdate):
    try:
        data = detection_service.update_detection_config(update)
        return ok("Detection config updated successfully.", data)
    except Exception as error:
        return error_from_exception(error)


@router.put("", response_model=ApiResponse)
def replace_detection_config(config: DetectionConfig):
    try:
        data = detection_service.replace_detection_config(config)
        return ok("Detection config replaced successfully.", data)
    except Exception as error:
        return error_from_exception(error)


@router.delete("", response_model=ApiResponse)
def delete_detection_config():
    try:
        data = detection_service.delete_detection_config()
        return ok("Detection config reset to defaults successfully.", data)
    except Exception as error:
        return error_from_exception(error)
