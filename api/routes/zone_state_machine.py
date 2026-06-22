from fastapi import APIRouter, HTTPException

from api.models.zone_state_machine import (
    ZoneStateMachineConfig,
    ZoneStateMachineConfigUpdate,
)
from api.services import zone_state_machine as zone_state_machine_service


router = APIRouter()


@router.get("", response_model=ZoneStateMachineConfig)
def get_zone_state_machine_config():
    try:
        return zone_state_machine_service.get_zone_state_machine_config()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("", response_model=ZoneStateMachineConfig)
def update_zone_state_machine_config(update: ZoneStateMachineConfigUpdate):
    try:
        return zone_state_machine_service.update_zone_state_machine_config(update)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("", response_model=ZoneStateMachineConfig)
def replace_zone_state_machine_config(config: ZoneStateMachineConfig):
    try:
        return zone_state_machine_service.update_zone_state_machine_config(
            ZoneStateMachineConfigUpdate(**config.model_dump())
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
