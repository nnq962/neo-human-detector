from typing import Optional

from pydantic import BaseModel, Field


class DetectionConfig(BaseModel):
    model_id: Optional[str] = None
    batch_size: int = Field(1, ge=1, le=8)
    conf: float = Field(0.5, ge=0.0, le=1.0)
    verbose: bool = False


class DetectionConfigUpdate(BaseModel):
    model_id: Optional[str] = None
    batch_size: Optional[int] = Field(None, ge=1, le=8)
    conf: Optional[float] = Field(None, ge=0.0, le=1.0)
    verbose: Optional[bool] = None
