from pydantic import BaseModel, Field
from typing import Literal, Optional


class DetectorStatus(BaseModel):
    is_running: bool
    model_path: Optional[str] = None
    task: Optional[str] = None
    conf: Optional[float] = None
    batch_size: Optional[int] = None
    verbose: Optional[bool] = None
    cameras: list[dict] = Field(default_factory=list)


class DetectionConfig(BaseModel):
    task: Literal["detect", "pose"] = "pose"
    model_size: Literal["nano", "medium"] = "medium"
    batch_size: Literal[1, 2] = 1
    conf: float = Field(0.5, ge=0.0, le=1.0)
    tracker: str = "bytetrack.yaml"
    verbose: bool = False


class DetectionConfigUpdate(BaseModel):
    task: Optional[Literal["detect", "pose"]] = None
    model_size: Optional[Literal["nano", "medium"]] = None
    batch_size: Optional[Literal[1, 2]] = None
    conf: Optional[float] = Field(None, ge=0.0, le=1.0)
    tracker: Optional[str] = None
    verbose: Optional[bool] = None


class DetectorSettings(BaseModel):
    auto_start: bool = False
    detection: DetectionConfig = Field(default_factory=DetectionConfig)


class DetectorSettingsUpdate(BaseModel):
    auto_start: Optional[bool] = None
    detection: Optional[DetectionConfigUpdate] = None
