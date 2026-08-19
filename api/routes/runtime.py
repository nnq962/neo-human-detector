from fastapi import APIRouter, status
from typing import Optional

from api.models.response import ApiResponse
from api.models.runtime import (
    RuntimeCommandRequest,
    RuntimeSettings,
    RuntimeSettingsUpdate,
    RuntimeTaskCreateRequest,
)
from api.routes.responses import error_from_exception, error_response, ok
from api.services import runtime as runtime_service


router = APIRouter()


@router.get("/status", response_model=ApiResponse)
def get_runtime_status():
    """Trả trạng thái runtime hiện tại."""
    try:
        return ok("Runtime status loaded successfully.", runtime_service.get_runtime_status())
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)


# ─────────────────────────────────────────────────────────────────────────────
@router.get("/config", response_model=ApiResponse)
def get_runtime_config():
    """Trả cấu hình camera và tự động khởi động của runtime."""
    try:
        return ok("Runtime config loaded successfully.", runtime_service.get_runtime_config())
    except Exception as error:
        return error_from_exception(error)


# ─────────────────────────────────────────────────────────────────────────────
@router.patch("/config", response_model=ApiResponse)
def update_runtime_config(update: RuntimeSettingsUpdate):
    """Cập nhật một phần cấu hình runtime."""
    try:
        return ok("Runtime config updated successfully.", runtime_service.update_runtime_config(update))
    except Exception as error:
        return error_from_exception(error)


# ─────────────────────────────────────────────────────────────────────────────
@router.put("/config", response_model=ApiResponse)
def replace_runtime_config(settings: RuntimeSettings):
    """Thay thế toàn bộ cấu hình runtime."""
    try:
        return ok("Runtime config replaced successfully.", runtime_service.replace_runtime_config(settings))
    except Exception as error:
        return error_from_exception(error)


# ─────────────────────────────────────────────────────────────────────────────
@router.get("/tasks", response_model=ApiResponse)
def get_runtime_tasks():
    """Trả snapshot task của phiên runtime hiện tại."""
    try:
        return ok(
            "Runtime task snapshot loaded successfully.",
            runtime_service.get_runtime_tasks(),
        )
    except Exception as error:
        return error_from_exception(error)


# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/tasks",
    response_model=ApiResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_runtime_task(request: RuntimeTaskCreateRequest):
    """Tạo task thủ công từ điểm pixel trên camera runtime."""
    try:
        return ok(
            "Runtime task created successfully.",
            runtime_service.create_runtime_task(request),
        )
    except RuntimeError as error:
        return error_response(status.HTTP_409_CONFLICT, str(error))
    except Exception as error:
        return error_from_exception(error)


# ─────────────────────────────────────────────────────────────────────────────
@router.post("/tasks/{task_uid}/cancel", response_model=ApiResponse)
def cancel_runtime_task(task_uid: str):
    """Yêu cầu hủy task runtime theo UID từ nguồn zone hoặc manual."""
    try:
        return ok(
            "Runtime task cancellation requested successfully.",
            runtime_service.cancel_runtime_task(task_uid),
        )
    except RuntimeError as error:
        return error_response(status.HTTP_409_CONFLICT, str(error))
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)


# ─────────────────────────────────────────────────────────────────────────────
@router.post("/start", response_model=ApiResponse)
def start_runtime(command: Optional[RuntimeCommandRequest] = None):
    """Khởi động runtime."""
    try:
        return ok("Runtime started successfully.", runtime_service.start_runtime(command))
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)


# ─────────────────────────────────────────────────────────────────────────────
@router.post("/stop", response_model=ApiResponse)
def stop_runtime():
    """Dừng runtime."""
    try:
        return ok("Runtime stopped successfully.", runtime_service.stop_runtime())
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)


# ─────────────────────────────────────────────────────────────────────────────
@router.post("/restart", response_model=ApiResponse)
def restart_runtime(command: Optional[RuntimeCommandRequest] = None):
    """Khởi động lại runtime."""
    try:
        return ok("Runtime restarted successfully.", runtime_service.restart_runtime(command))
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)


# ─────────────────────────────────────────────────────────────────────────────
@router.post("/reload", response_model=ApiResponse)
def reload_runtime(command: Optional[RuntimeCommandRequest] = None):
    """Nạp lại cấu hình runtime."""
    try:
        return ok("Runtime reloaded successfully.", runtime_service.reload_runtime(command))
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)
