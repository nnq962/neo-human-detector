from typing import Optional

from pydantic import BaseModel, Field


class DetectionConfig(BaseModel):
    model_id: Optional[str] = None
    conf: float = Field(0.5, ge=0.0, le=1.0)
    verbose: bool = False


class DetectionConfigUpdate(BaseModel):
    model_id: Optional[str] = None
    conf: Optional[float] = Field(None, ge=0.0, le=1.0)
    verbose: Optional[bool] = None
