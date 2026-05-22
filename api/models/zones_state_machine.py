from typing import Literal, Optional

from pydantic import BaseModel, Field


class ZonesStateMachineConfig(BaseModel):
    zone_check_mode: Literal["center", "bottom_center"] = "center"
    confirm_enter_time: float = Field(5.0, ge=0.0)
    confirm_exit_time: float = Field(5.0, ge=0.0)
    pending_enter_miss_grace_time: float = Field(1.5, ge=0.0)


class ZonesStateMachineConfigUpdate(BaseModel):
    zone_check_mode: Optional[Literal["center", "bottom_center"]] = None
    confirm_enter_time: Optional[float] = Field(None, ge=0.0)
    confirm_exit_time: Optional[float] = Field(None, ge=0.0)
    pending_enter_miss_grace_time: Optional[float] = Field(None, ge=0.0)

