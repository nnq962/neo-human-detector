from pydantic import BaseModel, Field
from typing import Literal, Optional

class DetectorStatus(BaseModel):
    is_running: bool
    source: Optional[str] = None
    mode: Optional[Literal["head", "person"]] = None
    model_path: Optional[str] = None
    conf: Optional[float] = None
    vid_stride: Optional[int] = None
    verbose: Optional[bool] = None


class DetectorConfig(BaseModel):
    mode: Literal["head", "person"] = "head"
    model_size: Literal["nano", "medium"] = "nano"
    batch_size: Literal[1, 2, 4] = 1
    conf: float = Field(0.5, ge=0.0, le=1.0)
    vid_stride: int = Field(1, ge=1)
    verbose: bool = False


class DetectorConfigUpdate(BaseModel):
    mode: Optional[Literal["head", "person"]] = None
    model_size: Optional[Literal["nano", "medium"]] = None
    batch_size: Optional[Literal[1, 2, 4]] = None
    conf: Optional[float] = Field(None, ge=0.0, le=1.0)
    vid_stride: Optional[int] = Field(None, ge=1)
    verbose: Optional[bool] = None


class DetectorSettings(BaseModel):
    auto_start: bool = False
    detector: DetectorConfig = Field(default_factory=DetectorConfig)


class DetectorSettingsUpdate(BaseModel):
    auto_start: Optional[bool] = None
    detector: Optional[DetectorConfigUpdate] = None
