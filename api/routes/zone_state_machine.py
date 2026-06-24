from fastapi import APIRouter

from api.models.response import ApiResponse
from api.models.zone_state_machine import (
    ZoneStateMachineConfig,
    ZoneStateMachineConfigUpdate,
)
from api.routes.responses import error_from_exception, ok
from api.services import zone_state_machine as zone_state_machine_service


router = APIRouter()


@router.get("", response_model=ApiResponse)
def get_zone_state_machine_config():
    try:
        data = zone_state_machine_service.get_zone_state_machine_config()
        return ok("Zone state machine config loaded successfully.", data)
    except Exception as error:
        return error_from_exception(error)


@router.patch("", response_model=ApiResponse)
def update_zone_state_machine_config(update: ZoneStateMachineConfigUpdate):
    try:
        data = zone_state_machine_service.update_zone_state_machine_config(update)
        return ok("Zone state machine config updated successfully.", data)
    except Exception as error:
        return error_from_exception(error)


@router.put("", response_model=ApiResponse)
def replace_zone_state_machine_config(config: ZoneStateMachineConfig):
    try:
        data = zone_state_machine_service.update_zone_state_machine_config(
            ZoneStateMachineConfigUpdate(**config.model_dump())
        )
        return ok("Zone state machine config replaced successfully.", data)
    except Exception as error:
        return error_from_exception(error)
