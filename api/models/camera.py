from typing import List, Optional

from pydantic import BaseModel, Field


class GoalPose(BaseModel):
    x: float
    y: float
    theta: float


class Zone(BaseModel):
    id: Optional[str] = None
    name: str
    goal_pose: Optional[GoalPose] = None
    points: List[List[int]] = Field(default_factory=list)


class StreamConfig(BaseModel):
    source: str
    protocol: str = "tcp"
    on_demand: bool = True


class StreamConfigUpdate(BaseModel):
    source: Optional[str] = None
    protocol: Optional[str] = None
    on_demand: Optional[bool] = None


class CameraBase(BaseModel):
    name: str
    stream: StreamConfig
    enabled: bool = True
    zones: List[Zone] = Field(default_factory=list)


class CameraCreate(CameraBase):
    pass


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    stream: Optional[StreamConfigUpdate] = None
    enabled: Optional[bool] = None
    zones: Optional[List[Zone]] = None


class Camera(CameraBase):
    id: str
    webrtc_address: Optional[str] = None
