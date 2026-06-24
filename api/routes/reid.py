from fastapi import APIRouter

from api.models.response import ApiResponse
from api.models.reid import ReIdConfig, ReIdConfigUpdate
from api.routes.responses import error_from_exception, ok
from api.services import reid as reid_service


router = APIRouter()


@router.get("", response_model=ApiResponse)
def get_reid_config():
    try:
        return ok("ReID config loaded successfully.", reid_service.get_reid_config())
    except Exception as error:
        return error_from_exception(error)


@router.patch("", response_model=ApiResponse)
def update_reid_config(update: ReIdConfigUpdate):
    try:
        return ok("ReID config updated successfully.", reid_service.update_reid_config(update))
    except Exception as error:
        return error_from_exception(error)


@router.put("", response_model=ApiResponse)
def replace_reid_config(config: ReIdConfig):
    try:
        return ok("ReID config replaced successfully.", reid_service.replace_reid_config(config))
    except Exception as error:
        return error_from_exception(error)


@router.delete("", response_model=ApiResponse)
def delete_reid_config():
    try:
        reid_service.delete_reid_config()
        return ok("ReID config deleted successfully.")
    except Exception as error:
        return error_from_exception(error)
