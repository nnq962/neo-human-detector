from typing import Literal, Optional

from pydantic import BaseModel, Field


class DetectionConfig(BaseModel):
    task: Literal["detect", "pose"] = "pose"
    model_size: Literal["nano", "medium"] = "medium"
    batch_size: Literal[1, 2] = 1
    conf: float = Field(0.5, ge=0.0, le=1.0)
    verbose: bool = False


class DetectionConfigUpdate(BaseModel):
    task: Optional[Literal["detect", "pose"]] = None
    model_size: Optional[Literal["nano", "medium"]] = None
    batch_size: Optional[Literal[1, 2]] = None
    conf: Optional[float] = Field(None, ge=0.0, le=1.0)
    verbose: Optional[bool] = None
