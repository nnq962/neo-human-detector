"""Cấu hình runtime cho RobotDispatcherV2."""

from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RobotDispatchV2Config:
    """Các tùy chọn cho flow decision và thực thi lệnh robot V2."""

    enabled: bool = False
    use_reid: bool = False
    ack_timeout_seconds: float = 1.0
    max_retries: int = 10
    max_dispatch_attempts: int = 10
    retry_backoff_seconds: float = 1.0
    robot_rejection_cooldown_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.ack_timeout_seconds <= 0:
            raise ValueError("ack_timeout_seconds phải lớn hơn 0")
        if self.max_retries <= 0:
            raise ValueError("max_retries phải lớn hơn 0")
        if self.max_dispatch_attempts <= 0:
            raise ValueError("max_dispatch_attempts phải lớn hơn 0")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds không được âm")
        if self.robot_rejection_cooldown_seconds < 0:
            raise ValueError("robot_rejection_cooldown_seconds không được âm")
