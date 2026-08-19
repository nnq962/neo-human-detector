from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
def _polygon_area(points: List[List[int]]) -> float:
    """Tính diện tích có hướng tuyệt đối của polygon bằng công thức shoelace."""
    return abs(
        sum(
            current[0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * current[1]
            for index, current in enumerate(points)
        )
    ) / 2.0


class Zone(BaseModel):
    """Một vùng polygon hợp lệ trong hệ tọa độ pixel video."""

    id: Optional[str] = None
    name: str
    priority: Literal["low", "medium", "high"] = "low"
    service_point: Optional[List[int]] = Field(
        default=None,
        min_length=2,
        max_length=2,
    )
    points: List[List[int]] = Field(min_length=3)

    @field_validator("points")
    @classmethod
    def validate_polygon(cls, points: List[List[int]]) -> List[List[int]]:
        """Từ chối điểm sai shape, trùng nhau hoặc polygon có diện tích bằng 0."""
        if any(len(point) != 2 for point in points):
            raise ValueError("Mỗi điểm zone phải có đúng hai tọa độ.")
        if len({(point[0], point[1]) for point in points}) < 3:
            raise ValueError("Zone phải có ít nhất ba điểm phân biệt.")
        if _polygon_area(points) <= 0:
            raise ValueError("Các điểm zone không được thẳng hàng.")
        return points


class StreamConfig(BaseModel):
    source: str
    protocol: str = "tcp"
    on_demand: bool = True


class StreamConfigUpdate(BaseModel):
    source: Optional[str] = None
    protocol: Optional[str] = None
    on_demand: Optional[bool] = None


class CameraBase(BaseModel):
    name: str
    stream: StreamConfig
    enabled: bool = True
    zones: List[Zone] = Field(default_factory=list)


class CameraCreate(CameraBase):
    pass


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    stream: Optional[StreamConfigUpdate] = None
    enabled: Optional[bool] = None
    zones: Optional[List[Zone]] = None


class Camera(CameraBase):
    id: str
    webrtc_address: Optional[str] = None


class CalibrationImageSize(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class CalibrationPixelCoordinate(BaseModel):
    u: float
    v: float


class CalibrationWorldCoordinate(BaseModel):
    x: float
    y: float


class CalibrationPointInput(BaseModel):
    id: str = Field(min_length=1)
    pixel: CalibrationPixelCoordinate
    world: CalibrationWorldCoordinate
    robot_id: Optional[int] = None


class CalibrationPreviewRequest(BaseModel):
    image_size: CalibrationImageSize
    points: List[CalibrationPointInput] = Field(min_length=4)
    ransac_threshold_m: float = Field(default=0.10, gt=0)


class CalibrationApplyRequest(CalibrationPreviewRequest):
    accept_warning: bool = False


class CalibrationPredictedWorld(BaseModel):
    x: float
    y: float


class CalibrationPointResult(BaseModel):
    id: str
    valid: bool
    predicted_world: CalibrationPredictedWorld
    error_m: float
    validation_error_m: Optional[float] = None


class CalibrationQuality(BaseModel):
    valid_points: int
    total_points: int
    valid_ratio: float
    rmse_inlier_m: float
    rmse_all_m: float
    validation_rmse_m: Optional[float] = None
    rating: Literal["GOOD", "CHECK", "RECALIBRATE", "LIMITED"]


class CalibrationPreviewResult(BaseModel):
    camera_id: str
    image_size: CalibrationImageSize
    direction: Literal["pixel_to_world"]
    method: Literal["ransac"]
    ransac_threshold_m: float
    homography: List[List[float]]
    quality: CalibrationQuality
    points: List[CalibrationPointResult]


class CalibrationStoredPoint(BaseModel):
    id: str
    pixel: List[float] = Field(min_length=2, max_length=2)
    world: List[float] = Field(min_length=2, max_length=2)
    robot_id: Optional[int] = None
    valid: bool
    predicted_world: List[float] = Field(min_length=2, max_length=2)
    error_m: float
    validation_error_m: Optional[float] = None


class CameraCalibration(BaseModel):
    camera_id: str
    image_size: CalibrationImageSize
    direction: Literal["pixel_to_world"]
    method: Literal["ransac"]
    ransac_threshold_m: float
    homography: List[List[float]]
    quality: CalibrationQuality
    points: List[CalibrationStoredPoint]
    updated_at: str
