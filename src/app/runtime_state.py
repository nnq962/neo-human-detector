"""
Runtime state dùng chung cho app/orchestrator.

Class này lưu snapshot mới nhất của WebSocket payload và UART-like zone event.
Nó không tự gửi dữ liệu ra ngoài; nhiệm vụ gửi thật nên nằm ở output/integration
khác để runtime dễ test.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Dict, Optional


# ─────────────────────────────────────────────────────────────────────────────
def _empty_websocket_payload() -> Dict[str, Any]:
    """Tạo payload rỗng theo shape frontend đang đọc."""
    return {"cameras": {}}


# ─────────────────────────────────────────────────────────────────────────────
def _empty_zone_event_payload() -> Dict[str, Any]:
    """Tạo payload event zone rỗng theo format state machine."""
    return {"detected": [], "cleared": []}


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class RuntimeState:
    """
    Lưu state mới nhất của app runtime theo kiểu thread-safe nhẹ.

    Sau này WebSocket server hoặc UART sender có thể đọc snapshot từ đây mà không
    cần biết vòng lặp detector đang chạy ra sao.
    """

    latest_ws_payload  : Dict[str, Any] = field(default_factory=_empty_websocket_payload)
    latest_uart_payload: Dict[str, Any] = field(default_factory=_empty_zone_event_payload)
    is_running         : bool           = False

    def __post_init__(self) -> None:
        """Khởi tạo lock nội bộ sau dataclass init."""
        self._lock = RLock()

    def mark_running(self, value: bool) -> None:
        """Cập nhật trạng thái runtime đang chạy hay đã dừng."""
        with self._lock:
            self.is_running = bool(value)

    def update_camera_payload(self, camera_id: str, payload: Dict[str, Any]) -> None:
        """Lưu payload mới nhất của một camera."""
        with self._lock:
            cameras = self.latest_ws_payload.setdefault("cameras", {})
            cameras[str(camera_id)] = payload

    def update_zone_event_payload(self, payload: Dict[str, Any]) -> None:
        """Lưu event zone mới nhất nếu state machine phát sinh detected/cleared."""
        with self._lock:
            self.latest_uart_payload = payload

    def get_websocket_snapshot(self) -> Dict[str, Any]:
        """Trả bản copy payload WebSocket mới nhất để consumer đọc an toàn."""
        with self._lock:
            return deepcopy(self.latest_ws_payload)

    def get_uart_snapshot(self) -> Dict[str, Any]:
        """Trả bản copy payload zone event mới nhất."""
        with self._lock:
            return deepcopy(self.latest_uart_payload)

    def reset(self) -> None:
        """Reset toàn bộ runtime state về trạng thái ban đầu."""
        with self._lock:
            self.latest_ws_payload = _empty_websocket_payload()
            self.latest_uart_payload = _empty_zone_event_payload()
            self.is_running = False

    def latest_camera_payload(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Lấy payload mới nhất của một camera nếu có."""
        with self._lock:
            payload = self.latest_ws_payload.get("cameras", {}).get(str(camera_id))
            return deepcopy(payload) if payload is not None else None
