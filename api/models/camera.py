from typing import List, Optional

from pydantic import BaseModel, Field


class GoalPose(BaseModel):
    x: float
    y: float
    theta: float


class Zone(BaseModel):
    name: str
    goal_pose: Optional[GoalPose] = None
    points: List[List[int]] = Field(default_factory=list)


class CameraBase(BaseModel):
    name: str
    source: str
    source_protocol: str = "tcp"
    source_on_demand: bool = True
    enabled: bool = True
    zones: List[Zone] = Field(default_factory=list)


class CameraCreate(CameraBase):
    pass


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    source: Optional[str] = None
    source_protocol: Optional[str] = None
    source_on_demand: Optional[bool] = None
    enabled: Optional[bool] = None
    zones: Optional[List[Zone]] = None


class Camera(CameraBase):
    id: str
    webrtc_address: Optional[str] = None
