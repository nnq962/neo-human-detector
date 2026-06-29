"""
Dispatcher sinh request robot từ trạng thái zone trong runtime.
"""

from __future__ import annotations

import time
import math
from typing import Dict, List, Optional, Sequence

from src.robot_dispatch.datatypes import (
    RobotDispatchConfig,
    RobotDispatchEvent,
    RobotDispatchRequest,
    build_zone_dispatch_request,
)
from src.robot_dispatch.transport import LoggingRobotTransport, RobotTransport
from src.zones_management import Zone, ZoneState
from utils import LOGGER


ROBOT_AT_ZONE_DISTANCE_THRESHOLD = 0.1


# ─────────────────────────────────────────────────────────────────────────────
class RobotDispatcher:
    """
    Theo dõi transition zone và phát request robot đúng một lần cho mỗi event.

    Runtime gọi dispatcher sau khi `ZoneStateMachine.update(...)` đã cập nhật
    `zone.state`. Dispatcher giữ state cũ theo `zone.key` để tránh gửi trùng
    request ở mọi frame khi zone vẫn đang OCCUPIED.
    """

    def __init__(
        self,
        config: Optional[RobotDispatchConfig] = None,
        transport: Optional[RobotTransport] = None,
    ) -> None:
        """Khởi tạo dispatcher với transport gửi request."""
        self.config = config or RobotDispatchConfig()
        self.transport = transport or LoggingRobotTransport()
        self._previous_states: Dict[str, ZoneState] = {}
        self._latest_zone_items: Dict[str, dict] = {}

    def process_zones(
        self,
        zones: Sequence[Zone],
        *,
        timestamp: Optional[float] = None,
    ) -> List[RobotDispatchRequest]:
        """Xử lý danh sách zone và gửi các request phát sinh theo batch."""
        if not self.config.enabled:
            return []

        current_timestamp = time.time() if timestamp is None else float(timestamp)
        requests: List[RobotDispatchRequest] = []

        for zone in zones:
            self._latest_zone_items[zone.key] = _build_zone_snapshot(zone)
            request = self._build_transition_request(
                zone,
                timestamp=current_timestamp,
            )
            self._previous_states[zone.key] = zone.state

            if request is None:
                continue

            requests.append(request)

        if requests:
            self._send_batch(requests)

        return requests

    def build_sync_payload(self, latest_received_data: Optional[dict] = None) -> dict:
        """Tạo payload sync từ trạng thái zone mới nhất dispatcher đã ghi nhận."""
        robot_x, robot_y = _extract_robot_xy(latest_received_data)
        payload = {
            "detected": [],
            "cleared": [],
        }

        for item in self._latest_zone_items.values():
            if item["state"] == ZoneState.EMPTY.value:
                payload["cleared"].append(_build_uart_zone_item(item))
                continue
            if item["state"] != ZoneState.OCCUPIED.value:
                continue

            if _is_robot_at_zone(item, robot_x=robot_x, robot_y=robot_y):
                LOGGER.info(
                    "Lược bỏ zone %s khỏi lệnh sync vì robot đang đứng tại đây.",
                    item["zone_key"],
                )
                continue

            payload["detected"].append(_build_uart_zone_item(item))

        return payload

    def send_sync(self, latest_received_data: Optional[dict] = None) -> dict:
        """Gửi lại trạng thái zone hiện tại cho robot khi nhận lệnh sync."""
        payload = self.build_sync_payload(latest_received_data)
        self._send_sync_payload(payload)
        return payload

    def reset(self, zones: Optional[Sequence[Zone]] = None) -> None:
        """Reset state đã ghi nhớ, hoặc seed lại từ danh sách zone hiện tại."""
        self._previous_states.clear()
        self._latest_zone_items.clear()
        if zones is None:
            return

        for zone in zones:
            self._previous_states[zone.key] = zone.state
            self._latest_zone_items[zone.key] = _build_zone_snapshot(zone)

    def close(self) -> None:
        """Đóng transport và xóa state nội bộ."""
        try:
            self.transport.close()
        finally:
            self._previous_states.clear()
            self._latest_zone_items.clear()

    def _build_transition_request(
        self,
        zone: Zone,
        *,
        timestamp: float,
    ) -> Optional[RobotDispatchRequest]:
        """Tạo request nếu zone vừa chuyển sang trạng thái cần gửi robot."""
        previous_state = self._previous_states.get(zone.key)

        if self._should_emit_occupied(previous_state, zone.state):
            return build_zone_dispatch_request(
                zone=zone,
                event=RobotDispatchEvent.ZONE_OCCUPIED,
                timestamp=timestamp,
            )

        if self._should_emit_cleared(previous_state, zone.state):
            return build_zone_dispatch_request(
                zone=zone,
                event=RobotDispatchEvent.ZONE_CLEARED,
                timestamp=timestamp,
            )

        return None

    def _should_emit_occupied(
        self,
        previous_state: Optional[ZoneState],
        current_state: ZoneState,
    ) -> bool:
        """Kiểm tra zone có vừa vào OCCUPIED và cần gửi request không."""
        if not self.config.emit_occupied:
            return False
        if current_state != ZoneState.OCCUPIED:
            return False
        return previous_state in {None, ZoneState.EMPTY, ZoneState.PENDING_ENTER}

    def _should_emit_cleared(
        self,
        previous_state: Optional[ZoneState],
        current_state: ZoneState,
    ) -> bool:
        """Kiểm tra zone có vừa được clear và cần gửi event không."""
        if not self.config.emit_cleared:
            return False
        if current_state != ZoneState.EMPTY:
            return False
        return previous_state in {ZoneState.OCCUPIED, ZoneState.PENDING_EXIT}

    def _send_batch(self, requests: Sequence[RobotDispatchRequest]) -> None:
        """Gửi batch request qua transport và xử lý lỗi theo cấu hình."""
        try:
            self.transport.send_batch(requests)
        except Exception as exc:
            if self.config.raise_on_transport_error:
                raise
            request_ids = [request.request_id for request in requests]
            LOGGER.error("Không gửi được batch request robot %s: %s", request_ids, exc)

    def _send_sync_payload(self, payload: dict) -> None:
        """Gửi payload sync qua transport và xử lý lỗi theo cấu hình."""
        try:
            self.transport.send_sync_payload(payload)
        except Exception as exc:
            if self.config.raise_on_transport_error:
                raise
            LOGGER.error("Không gửi được payload sync robot %s: %s", payload, exc)


# ─────────────────────────────────────────────────────────────────────────────
def _build_zone_snapshot(zone: Zone) -> dict:
    """Chụp trạng thái zone hiện tại thành dict độc lập với object runtime."""
    return {
        "camera_id": zone.camera_id,
        "camera_name": zone.camera_name,
        "zone_id": zone.id,
        "zone_key": zone.key,
        "zone_name": zone.name,
        "state": zone.state.value,
        "goal_pose": dict(zone.goal_pose),
    }


# ─────────────────────────────────────────────────────────────────────────────
def _build_uart_zone_item(item: dict) -> dict:
    """Tạo item zone theo format detected/cleared cũ."""
    return {
        "camera_id": item["camera_id"],
        "camera_name": item["camera_name"],
        "zone_key": item["zone_key"],
        "zone_name": item["zone_name"],
        "goal_pose": dict(item["goal_pose"]),
    }


# ─────────────────────────────────────────────────────────────────────────────
def _extract_robot_xy(latest_received_data: Optional[dict]) -> tuple[Optional[float], Optional[float]]:
    """Lấy tọa độ robot mới nhất từ dữ liệu UART nếu có."""
    if not latest_received_data:
        return None, None

    payload = latest_received_data.get("payload", {})
    if not isinstance(payload, dict):
        return None, None
    if "x" not in payload or "y" not in payload:
        return None, None

    try:
        return float(payload["x"]), float(payload["y"])
    except (TypeError, ValueError):
        return None, None


# ─────────────────────────────────────────────────────────────────────────────
def _is_robot_at_zone(
    item: dict,
    *,
    robot_x: Optional[float],
    robot_y: Optional[float],
) -> bool:
    """Kiểm tra robot có đang đứng đủ gần goal_pose của zone không."""
    if robot_x is None or robot_y is None:
        return False

    goal_pose = item.get("goal_pose", {})
    try:
        goal_x = float(goal_pose.get("x", 0.0))
        goal_y = float(goal_pose.get("y", 0.0))
    except (TypeError, ValueError):
        return False

    distance = math.sqrt((robot_x - goal_x) ** 2 + (robot_y - goal_y) ** 2)
    return distance < ROBOT_AT_ZONE_DISTANCE_THRESHOLD
