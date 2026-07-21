from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


RuntimeState = Literal["stopped", "starting", "running", "stopping", "error"]
RuntimeTaskState = Literal[
    "WAITING_ROBOT",
    "ASSIGNING",
    "ASSIGNED",
    "IN_PROGRESS",
    "CANCELING",
    "COMPLETED",
    "FAILED",
    "CANCELED",
]


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


class RuntimeTaskGoalPose(BaseModel):
    x: float
    y: float
    theta: float


class RuntimeTask(BaseModel):
    uid: str
    task_id: Optional[int] = None
    robot_id: Optional[int] = None
    camera_id: str
    camera_name: str
    zone_id: str
    zone_name: str
    goal_pose: RuntimeTaskGoalPose
    person_global_id: Optional[int] = None
    person_similarity: Optional[float] = None
    person_track_id: Optional[int] = None
    status: RuntimeTaskState
    retry_count: int = 0
    assigned_at: str
    updated_at: str
    completed_at: Optional[str] = None


class RuntimeTaskSnapshot(BaseModel):
    sequence: int
    total: int
    active: int
    completed: int
    canceled: int
    failed: int
    tasks: List[RuntimeTask] = Field(default_factory=list)
