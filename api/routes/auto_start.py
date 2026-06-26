from fastapi import APIRouter

from api.models.auto_start import AutoStartConfig, AutoStartConfigUpdate
from api.models.response import ApiResponse
from api.routes.responses import error_from_exception, ok
from api.services import auto_start as auto_start_service


router = APIRouter()


@router.get("", response_model=ApiResponse)
def get_auto_start_config():
    try:
        return ok(
            "Auto-start config loaded successfully.",
            auto_start_service.get_auto_start_config(),
        )
    except Exception as error:
        return error_from_exception(error)


@router.patch("", response_model=ApiResponse)
def update_auto_start_config(update: AutoStartConfigUpdate):
    try:
        return ok(
            "Auto-start config updated successfully.",
            auto_start_service.update_auto_start_config(update),
        )
    except Exception as error:
        return error_from_exception(error)


@router.put("", response_model=ApiResponse)
def replace_auto_start_config(config: AutoStartConfig):
    try:
        return ok(
            "Auto-start config replaced successfully.",
            auto_start_service.replace_auto_start_config(config),
        )
    except Exception as error:
        return error_from_exception(error)
