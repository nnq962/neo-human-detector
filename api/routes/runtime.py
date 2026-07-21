from fastapi import APIRouter
from typing import Optional

from api.models.response import ApiResponse
from api.models.runtime import RuntimeCommandRequest
from api.routes.responses import error_from_exception, ok
from api.services import runtime as runtime_service


router = APIRouter()


@router.get("/status", response_model=ApiResponse)
def get_runtime_status():
    try:
        return ok("Runtime status loaded successfully.", runtime_service.get_runtime_status())
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)


@router.get("/tasks", response_model=ApiResponse)
def get_runtime_tasks():
    try:
        return ok(
            "Runtime task snapshot loaded successfully.",
            runtime_service.get_runtime_tasks(),
        )
    except Exception as error:
        return error_from_exception(error)


@router.post("/start", response_model=ApiResponse)
def start_runtime(command: Optional[RuntimeCommandRequest] = None):
    try:
        return ok("Runtime started successfully.", runtime_service.start_runtime(command))
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)


@router.post("/stop", response_model=ApiResponse)
def stop_runtime():
    try:
        return ok("Runtime stopped successfully.", runtime_service.stop_runtime())
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)


@router.post("/restart", response_model=ApiResponse)
def restart_runtime(command: Optional[RuntimeCommandRequest] = None):
    try:
        return ok("Runtime restarted successfully.", runtime_service.restart_runtime(command))
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)


@router.post("/reload", response_model=ApiResponse)
def reload_runtime(command: Optional[RuntimeCommandRequest] = None):
    try:
        return ok("Runtime reloaded successfully.", runtime_service.reload_runtime(command))
    except Exception as error:
        return error_from_exception(error, conflict_on_value_error=True)
