from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


RuntimeState = Literal["stopped", "starting", "running", "stopping", "error"]


class RuntimeCommandRequest(BaseModel):
    config_path: Optional[str] = None
    preview: Optional[bool] = None


class RuntimeCameraStatus(BaseModel):
    id: str
    name: str
    source: str
    zones: int = 0
    fps: Optional[float] = None
    zone_states: Dict[str, str] = Field(default_factory=dict)


class RuntimeStatus(BaseModel):
    state: RuntimeState
    is_running: bool
    thread_alive: bool
    config_path: Optional[str] = None
    preview: Optional[bool] = None
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    uptime_seconds: Optional[float] = None
    cameras: List[RuntimeCameraStatus] = Field(default_factory=list)
    last_error: Optional[str] = None
