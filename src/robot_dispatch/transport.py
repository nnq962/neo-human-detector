"""
Transport gửi request robot ra hệ thống bên ngoài.
"""

from __future__ import annotations

from typing import List, Protocol, Sequence

from utils import LOGGER

from src.robot_dispatch.datatypes import RobotDispatchRequest


# ─────────────────────────────────────────────────────────────────────────────
class RobotTransport(Protocol):
    """Interface tối thiểu cho lớp gửi request robot."""

    def send_batch(self, requests: Sequence[RobotDispatchRequest]) -> None:
        """Gửi một batch request robot."""

    def send_sync_payload(self, payload: dict) -> None:
        """Gửi payload sync trạng thái zone hiện tại."""

    def close(self) -> None:
        """Đóng tài nguyên transport nếu có."""


# ─────────────────────────────────────────────────────────────────────────────
class LoggingRobotTransport:
    """Transport mặc định chỉ log payload để kiểm tra luồng dispatcher."""

    def send_batch(self, requests: Sequence[RobotDispatchRequest]) -> None:
        """Ghi batch request robot ra log thay vì gửi network/UART thật."""
        payload = {
            "count": len(requests),
            "requests": [request.to_dict() for request in requests],
        }
        LOGGER.info("Robot dispatch batch: %s", payload)

    def send_sync_payload(self, payload: dict) -> None:
        """Ghi payload sync ra log thay vì gửi network/UART thật."""
        LOGGER.info("Robot dispatch sync payload: %s", payload)

    def close(self) -> None:
        """Đóng transport log, hiện không có tài nguyên cần giải phóng."""


# ─────────────────────────────────────────────────────────────────────────────
class InMemoryRobotTransport:
    """Transport lưu request trong bộ nhớ, hữu ích cho test hoặc debug."""

    def __init__(self) -> None:
        """Khởi tạo danh sách request và batch rỗng."""
        self.requests: List[RobotDispatchRequest] = []
        self.batches: List[List[RobotDispatchRequest]] = []
        self.sync_payloads: List[dict] = []

    def send_batch(self, requests: Sequence[RobotDispatchRequest]) -> None:
        """Lưu batch request vào danh sách nội bộ."""
        batch = list(requests)
        self.batches.append(batch)
        self.requests.extend(batch)

    def send_sync_payload(self, payload: dict) -> None:
        """Lưu payload sync vào danh sách nội bộ."""
        self.sync_payloads.append(payload)

    def close(self) -> None:
        """Xóa toàn bộ request đã lưu."""
        self.requests.clear()
        self.batches.clear()
        self.sync_payloads.clear()
