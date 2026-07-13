"""Cấu hình runtime cho RobotDispatcherV2."""

from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RobotDispatchV2Config:
    """Các tùy chọn cần thiết cho flow dispatch không-ReID hiện tại."""

    enabled: bool = False
    ack_timeout_seconds: float = 1.0
    max_retries: int = 5

    def __post_init__(self) -> None:
        if self.ack_timeout_seconds <= 0:
            raise ValueError("ack_timeout_seconds phải lớn hơn 0")
        if self.max_retries <= 0:
            raise ValueError("max_retries phải lớn hơn 0")
