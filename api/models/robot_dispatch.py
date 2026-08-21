"""Model API cho cấu hình auto-dispatch robot."""

from typing import Optional

from pydantic import BaseModel, Field


class RobotDispatchConfig(BaseModel):
    """Cấu hình đầy đủ của RobotDispatcher V2."""

    enabled: bool = False
    use_reid: bool = False
    ack_timeout_seconds: float = Field(1.0, gt=0.0)
    max_retries: int = Field(10, ge=1)
    max_dispatch_attempts: int = Field(10, ge=1)
    retry_backoff_seconds: float = Field(1.0, ge=0.0)
    robot_rejection_cooldown_seconds: float = Field(5.0, ge=0.0)


class RobotDispatchConfigUpdate(BaseModel):
    """Các trường auto-dispatch cho phép cập nhật một phần."""

    enabled: Optional[bool] = None
    use_reid: Optional[bool] = None
    ack_timeout_seconds: Optional[float] = Field(None, gt=0.0)
    max_retries: Optional[int] = Field(None, ge=1)
    max_dispatch_attempts: Optional[int] = Field(None, ge=1)
    retry_backoff_seconds: Optional[float] = Field(None, ge=0.0)
    robot_rejection_cooldown_seconds: Optional[float] = Field(None, ge=0.0)
