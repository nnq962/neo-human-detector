"""Endpoint cấu hình auto-dispatch robot."""

from fastapi import APIRouter

from api.models.response import ApiResponse
from api.models.robot_dispatch import RobotDispatchConfig, RobotDispatchConfigUpdate
from api.routes.responses import error_from_exception, ok
from api.services import robot_dispatch as robot_dispatch_service


router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
@router.get("", response_model=ApiResponse)
def get_robot_dispatch_config():
    """Trả cấu hình auto-dispatch robot hiện tại."""
    try:
        return ok("Robot dispatch config loaded successfully.", robot_dispatch_service.get_robot_dispatch_config())
    except Exception as error:
        return error_from_exception(error)


# ─────────────────────────────────────────────────────────────────────────────
@router.patch("", response_model=ApiResponse)
def update_robot_dispatch_config(update: RobotDispatchConfigUpdate):
    """Cập nhật một phần cấu hình auto-dispatch robot."""
    try:
        return ok("Robot dispatch config updated successfully.", robot_dispatch_service.update_robot_dispatch_config(update))
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)


# ─────────────────────────────────────────────────────────────────────────────
@router.put("", response_model=ApiResponse)
def replace_robot_dispatch_config(config: RobotDispatchConfig):
    """Thay thế toàn bộ cấu hình auto-dispatch robot."""
    try:
        return ok("Robot dispatch config replaced successfully.", robot_dispatch_service.replace_robot_dispatch_config(config))
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)
