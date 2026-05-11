from pydantic import BaseModel, Field
from typing import List, Optional

class DetectorConfig(BaseModel):
    source: str = "rtsp://admin:phenikaaneo%40@192.168.0.150:554/Streaming/Channels/101"
    model_path: str = "models/head/yolo8n_rknn_model"
    conf: float = Field(0.70, ge=0.0, le=1.0)
    zone_check_mode: str = "center"
    vid_stride: int = Field(1, ge=1)
    verbose: bool = True

class UartConfig(BaseModel):
    port: str = "/dev/ttyS4"
    baudrate: int = 115200

class GoalPoseConfig(BaseModel):
    x: float
    y: float
    theta: float

class ZoneConfig(BaseModel):
    name: str = "ghe1"
    goal_pose: Optional[GoalPoseConfig] = None
    points: List[List[int]] = Field(
        default=[[86, 722], [426, 718], [380, 1010], [45, 1014]]
    )

class AppConfig(BaseModel):
    auto_start: bool = False
    detector: DetectorConfig = Field(default_factory=DetectorConfig)
    uart: UartConfig = Field(default_factory=UartConfig)
    zones: Optional[List[ZoneConfig]] = Field(default_factory=list)
