from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


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
ALLOWED_RUNTIME_BATCH_SIZES = frozenset({1, 2, 4})


class RuntimeSettings(BaseModel):
    """Cấu hình vòng đời và danh sách camera của runtime."""

    auto_start: bool = False
    camera_ids: List[str] = Field(default_factory=list)

    # ─────────────────────────────────────────────────────────────────────────
    @field_validator("camera_ids")
    @classmethod
    def validate_camera_ids(cls, values: List[str]) -> List[str]:
        """Chuẩn hóa ID camera và từ chối giá trị rỗng hoặc trùng nhau."""
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("Camera ID không được để trống.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Danh sách camera runtime không được chứa ID trùng nhau.")
        return normalized

    # ─────────────────────────────────────────────────────────────────────────
    @property
    def batch_size(self) -> int:
        """Trả batch size được suy ra từ số camera đã chọn."""
        return len(self.camera_ids)


class RuntimeSettingsUpdate(BaseModel):
    """Các trường runtime cho phép cập nhật một phần."""

    auto_start: Optional[bool] = None
    camera_ids: Optional[List[str]] = None


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


class RuntimeInferenceMetric(BaseModel):
    """Thống kê thời gian inference của một model trong runtime."""

    last_ms: float
    average_ms: float
    min_ms: float
    max_ms: float
    sample_count: int


class RuntimePerformanceStatus(BaseModel):
    """Các metric inference hiện có của runtime."""

    yolo: Optional[RuntimeInferenceMetric] = None
    reid: Optional[RuntimeInferenceMetric] = None


class RuntimeStatus(BaseModel):
    state: RuntimeState
    is_running: bool
    thread_alive: bool
    config_path: Optional[str] = None
    preview: Optional[bool] = None
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    uptime_seconds: Optional[float] = None
    batch_size: int = 0
    cameras: List[RuntimeCameraStatus] = Field(default_factory=list)
    performance: RuntimePerformanceStatus = Field(default_factory=RuntimePerformanceStatus)
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
