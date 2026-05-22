from fastapi import APIRouter, HTTPException

from api.models.zones_state_machine import (
    ZonesStateMachineConfig,
    ZonesStateMachineConfigUpdate,
)
from api.services import zones_state_machine as zones_state_machine_service


router = APIRouter()


@router.get("", response_model=ZonesStateMachineConfig)
def get_zones_state_machine_config():
    try:
        return zones_state_machine_service.get_zones_state_machine_config()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("", response_model=ZonesStateMachineConfig)
def update_zones_state_machine_config(update: ZonesStateMachineConfigUpdate):
    try:
        return zones_state_machine_service.update_zones_state_machine_config(update)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("", response_model=ZonesStateMachineConfig)
def replace_zones_state_machine_config(config: ZonesStateMachineConfig):
    try:
        return zones_state_machine_service.update_zones_state_machine_config(
            ZonesStateMachineConfigUpdate(**config.model_dump())
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

