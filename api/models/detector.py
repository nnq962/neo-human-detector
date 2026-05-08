from pydantic import BaseModel
from typing import Optional

class DetectorStatus(BaseModel):
    is_running: bool
    source: Optional[str] = None
    model_path: Optional[str] = None
    conf: Optional[float] = None
    vid_stride: Optional[int] = None
    verbose: Optional[bool] = None