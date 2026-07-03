"""
Dispatcher sinh request robot từ trạng thái zone trong runtime.
NOTE: Hoạt động với 1 zone 1 người.
"""

from __future__ import annotations

import time
import math
from typing import Dict, List, Optional, Sequence, Set

from src.detection.datatypes import Detection, InferenceFrame
from src.robot_dispatch.datatypes import (
    PersonServiceRecord,
    PersonServiceState,
    RobotDispatchConfig,
    RobotDispatchEvent,
    RobotDispatchRequest,
    build_zone_dispatch_request,
)
from src.robot_dispatch.event_store import robot_dispatch_events
from src.robot_dispatch.transport import LoggingRobotTransport, RobotTransport
from src.zones_management import Zone, ZoneState
from utils import LOGGER


ROBOT_AT_ZONE_DISTANCE_THRESHOLD = 0.1
ROBOT_SERVICE_STATUS_TO_STATE = {
    "serving": PersonServiceState.SERVING,
    "served": PersonServiceState.SERVED,
    "failed": PersonServiceState.FAILED,
}
BLOCKING_PERSON_SERVICE_STATES = {
    PersonServiceState.REQUESTED,
    PersonServiceState.SERVING,
    PersonServiceState.SERVED,
    PersonServiceState.FAILED,
}


# ─────────────────────────────────────────────────────────────────────────────
class RobotDispatcher:
    """
    Theo dõi transition zone và phát request robot đúng một lần cho mỗi event.

    Runtime gọi dispatcher sau khi `ZoneStateMachine.update(...)` đã cập nhật
    `zone.state`. Dispatcher giữ state cũ theo zone id để tránh gửi trùng
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
        self._person_service_states: Dict[int, PersonServiceRecord] = {}
        self._last_zone_people: Dict[str, dict] = {}
        self._zone_fallback_requests: Set[str] = set()
        self._zones_cleared_after_request: Set[str] = set()
        self._logged_requested_skips: Set[tuple[int, str]] = set()

    def process_zones(
        self,
        zones: Sequence[Zone],
        *,
        timestamp: Optional[float] = None,
        detection_frame: Optional[InferenceFrame] = None,
        zone_names: Optional[Sequence[Optional[str]]] = None,
        reid_enabled: bool = False,
    ) -> List[RobotDispatchRequest]:
        """Xử lý danh sách zone và gửi các request phát sinh theo batch."""
        if not self.config.enabled:
            return []

        current_timestamp = time.time() if timestamp is None else float(timestamp)
        requests: List[RobotDispatchRequest] = []

        for zone in zones:
            zone_identity = _zone_identity(zone)
            self._latest_zone_items[zone_identity] = _build_zone_snapshot(zone)
            if zone.state == ZoneState.EMPTY:
                self._zone_fallback_requests.discard(zone_identity)
                if self._has_requested_person_for_zone(zone_identity):
                    self._zones_cleared_after_request.add(zone_identity)
                self._clear_logged_skips_for_zone(zone_identity)

            request = self._build_request(
                zone,
                detection_frame=detection_frame,
                zone_names=zone_names,
                timestamp=current_timestamp,
                reid_enabled=reid_enabled,
            )
            self._previous_states[zone_identity] = zone.state

            if request is None:
                continue

            requests.append(request)

        if requests:
            self._publish_sent_events(requests)

        if requests and self._send_batch(requests):
            self._mark_requested_people(requests)

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
                    item["zone_id"],
                )
                continue

            payload["detected"].append(_build_uart_zone_item(item))

        return payload

    def send_sync(self, latest_received_data: Optional[dict] = None) -> dict:
        """Gửi lại trạng thái zone hiện tại cho robot khi nhận lệnh sync."""
        payload = self.build_sync_payload(latest_received_data)
        self._send_sync_payload(payload)
        return payload

    def get_person_service_states(self) -> dict[int, str]:
        """Trả trạng thái phục vụ hiện tại theo global_id."""
        return {
            global_id: record.state.value
            for global_id, record in self._person_service_states.items()
        }

    def handle_robot_service_feedback(self, payload: dict) -> Optional[PersonServiceRecord]:
        """Cập nhật trạng thái phục vụ từ JSON feedback robot gửi qua UART."""
        if not isinstance(payload, dict):
            LOGGER.warning("Bỏ qua robot_service feedback không hợp lệ: %s", payload)
            return None

        status = payload.get("status")
        zone_id = payload.get("zone_id")
        next_state = ROBOT_SERVICE_STATUS_TO_STATE.get(str(status))

        has_zone_id = isinstance(zone_id, str) and bool(zone_id)
        if next_state is None or not has_zone_id:
            LOGGER.warning("Bỏ qua robot_service feedback không hợp lệ: %s", payload)
            return None

        global_id = _feedback_global_id(payload)
        if global_id is None:
            global_id = self._latest_service_global_id_for_zone_id(zone_id)

        if global_id is None:
            LOGGER.warning(
                "Không tìm thấy person service record cho robot_service feedback: %s",
                payload,
            )
            return None

        current = self._person_service_states.get(global_id)
        if current is None:
            LOGGER.warning(
                "Không tìm thấy global_id=%s cho robot_service feedback: %s",
                global_id,
                payload,
            )
            return None

        if current.zone_id != zone_id:
            LOGGER.warning(
                "Bỏ qua robot_service feedback lệch zone_id: global_id=%s expected=%s actual=%s",
                global_id,
                current.zone_id,
                zone_id,
            )
            return None

        updated = PersonServiceRecord(
            state=next_state,
            updated_at=time.time(),
            request_id=current.request_id,
            zone_id=current.zone_id,
        )
        self._person_service_states[global_id] = updated
        event_zone_item = self._zone_item_for_zone_id(zone_id)
        robot_dispatch_events.publish_service_update(
            status=str(status),
            zone=_build_event_zone_from_item(
                event_zone_item or self._latest_zone_items.get(current.zone_id),
                fallback_zone_id=current.zone_id,
                fallback_zone_name=current.zone_id or "",
            ),
            person={"global_id": global_id},
            request_id=current.request_id,
            reason=_optional_string(payload.get("reason")),
        )
        LOGGER.info(
            "Robot service feedback: global_id=%s zone_id=%s status=%s",
            global_id,
            zone_id,
            next_state.value,
        )
        return updated

    def reset(self, zones: Optional[Sequence[Zone]] = None) -> None:
        """Reset state đã ghi nhớ, hoặc seed lại từ danh sách zone hiện tại."""
        self._previous_states.clear()
        self._latest_zone_items.clear()
        self._person_service_states.clear()
        self._last_zone_people.clear()
        self._zone_fallback_requests.clear()
        self._zones_cleared_after_request.clear()
        self._logged_requested_skips.clear()
        if zones is None:
            return

        for zone in zones:
            zone_identity = _zone_identity(zone)
            self._previous_states[zone_identity] = zone.state
            self._latest_zone_items[zone_identity] = _build_zone_snapshot(zone)

    def close(self) -> None:
        """Đóng transport và xóa state nội bộ."""
        try:
            self.transport.close()
        finally:
            self._previous_states.clear()
            self._latest_zone_items.clear()
            self._person_service_states.clear()
            self._last_zone_people.clear()
            self._zone_fallback_requests.clear()
            self._zones_cleared_after_request.clear()
            self._logged_requested_skips.clear()

    def _build_request(
        self,
        zone: Zone,
        *,
        detection_frame: Optional[InferenceFrame],
        zone_names: Optional[Sequence[Optional[str]]],
        timestamp: float,
        reid_enabled: bool,
    ) -> Optional[RobotDispatchRequest]:
        """Tạo request theo policy zone-only hoặc ReID-aware."""
        if not self.config.require_reid:
            return self._build_transition_request(zone, timestamp=timestamp)

        if reid_enabled:
            request = self._build_identity_request(
                zone,
                detection_frame=detection_frame,
                zone_names=zone_names,
                timestamp=timestamp,
            )
            if request is not None:
                return request
            if zone.state == ZoneState.OCCUPIED and not self.config.fallback_without_reid:
                return None

        if zone.state == ZoneState.OCCUPIED and not self.config.fallback_without_reid:
            return None

        return self._build_transition_request(zone, timestamp=timestamp)

    def _build_identity_request(
        self,
        zone: Zone,
        *,
        detection_frame: Optional[InferenceFrame],
        zone_names: Optional[Sequence[Optional[str]]],
        timestamp: float,
    ) -> Optional[RobotDispatchRequest]:
        """Tạo request dựa trên người trong zone nếu người đó chưa được request."""
        if zone.state != ZoneState.OCCUPIED:
            if zone.state == ZoneState.EMPTY:
                return self._build_transition_request(zone, timestamp=timestamp)
            return None
        zone_identity = _zone_identity(zone)
        if zone_identity in self._zone_fallback_requests:
            return None

        person = _select_zone_person(
            zone,
            detection_frame=detection_frame,
            zone_names=zone_names,
        )
        if person is None or person.global_id is None:
            return None

        if self._should_block_person_request(person.global_id, zone, timestamp=timestamp):
            if self._is_person_served(person.global_id) and self._should_log_requested_skip(person.global_id, zone):
                self._log_requested_skip_once(person.global_id, zone)
            return None

        return build_zone_dispatch_request(
            zone=zone,
            event=RobotDispatchEvent.ZONE_OCCUPIED,
            timestamp=timestamp,
            person_global_id=person.global_id,
            similarity=person.similarity,
            metadata={
                "dispatch_reason": "identity_not_requested",
                "track_id": person.track_id,
                "reid_status": person.status,
            },
        )

    def _should_block_person_request(
        self,
        global_id: int,
        zone: Zone,
        *,
        timestamp: float,
    ) -> bool:
        """Kiểm tra service state hiện tại có chặn request mới hay không."""
        service = self._person_service_states.get(global_id)
        if service is None:
            return False
        if service.state not in BLOCKING_PERSON_SERVICE_STATES:
            return False
        if service.state == PersonServiceState.SERVED:
            return not self._is_service_expired(service, timestamp=timestamp)
        if service.state == PersonServiceState.SERVING:
            return not self._is_new_service_attempt(service, zone)
        if service.state == PersonServiceState.FAILED:
            return not self._is_new_service_attempt(service, zone)
        if service.state != PersonServiceState.REQUESTED:
            return False

        if self._is_new_service_attempt(service, zone):
            return False

        return not self._is_service_expired(service, timestamp=timestamp)

    def _is_new_service_attempt(self, service: PersonServiceRecord, zone: Zone) -> bool:
        """Người đã rời lượt cũ hoặc chuyển zone thì được tạo request mới nếu chưa SERVED."""
        zone_identity = _zone_identity(zone)
        if service.zone_id != zone_identity:
            return True
        return zone_identity in self._zones_cleared_after_request

    def _is_person_served(self, global_id: int) -> bool:
        """Kiểm tra người đã được robot phục vụ xong hay chưa."""
        service = self._person_service_states.get(global_id)
        return service is not None and service.state == PersonServiceState.SERVED

    def _service_ttl_seconds(self) -> Optional[float]:
        """Lấy TTL trạng thái phục vụ theo giây nếu được cấu hình."""
        if self.config.service_ttl_minutes is None:
            return None
        if self.config.service_ttl_minutes <= 0:
            return 0.0
        return self.config.service_ttl_minutes * 60.0

    def _is_service_expired(
        self,
        service: PersonServiceRecord,
        *,
        timestamp: float,
    ) -> bool:
        """Kiểm tra service state đã hết TTL để có thể tạo request mới."""
        ttl_seconds = self._service_ttl_seconds()
        if ttl_seconds is None:
            return False
        return timestamp - service.updated_at >= ttl_seconds

    def _build_transition_request(
        self,
        zone: Zone,
        *,
        timestamp: float,
    ) -> Optional[RobotDispatchRequest]:
        """Tạo request nếu zone vừa chuyển sang trạng thái cần gửi robot."""
        previous_state = self._previous_states.get(_zone_identity(zone))

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

    def _send_batch(self, requests: Sequence[RobotDispatchRequest]) -> bool:
        """Gửi batch request qua transport và xử lý lỗi theo cấu hình."""
        try:
            self.transport.send_batch(requests)
            return True
        except Exception as exc:
            if self.config.raise_on_transport_error:
                raise
            request_ids = [request.request_id for request in requests]
            LOGGER.error("Không gửi được batch request robot %s: %s", request_ids, exc)
            return False

    def _send_sync_payload(self, payload: dict) -> None:
        """Gửi payload sync qua transport và xử lý lỗi theo cấu hình."""
        try:
            self.transport.send_sync_payload(payload)
        except Exception as exc:
            if self.config.raise_on_transport_error:
                raise
            LOGGER.error("Không gửi được payload sync robot %s: %s", payload, exc)

    def _mark_requested_people(self, requests: Sequence[RobotDispatchRequest]) -> None:
        """Đánh dấu các người đã gửi request là REQUESTED."""
        for request in requests:
            if request.event != RobotDispatchEvent.ZONE_OCCUPIED:
                continue
            if request.person_global_id is None:
                self._mark_zone_fallback_request(request)
                continue
            self._person_service_states[request.person_global_id] = PersonServiceRecord(
                state=PersonServiceState.REQUESTED,
                updated_at=request.timestamp,
                request_id=request.request_id,
                zone_id=_request_zone_identity(request),
            )
            self._zones_cleared_after_request.discard(_request_zone_identity(request))

    def _has_requested_person_for_zone(self, zone_id: str) -> bool:
        """Kiểm tra zone từng gửi request người nào đó trong phiên hiện tại."""
        return any(
            record.zone_id == zone_id and record.state in BLOCKING_PERSON_SERVICE_STATES
            for record in self._person_service_states.values()
        )

    def _latest_service_global_id_for_zone_id(self, zone_id: str) -> Optional[int]:
        """Tìm person service record mới nhất của zone_id khi robot không gửi global_id."""
        candidates = [
            (global_id, record)
            for global_id, record in self._person_service_states.items()
            if record.zone_id == zone_id
            and record.state in BLOCKING_PERSON_SERVICE_STATES
        ]
        if not candidates:
            return None

        return max(candidates, key=lambda item: item[1].updated_at)[0]

    def _zone_item_for_zone_id(self, zone_id: str) -> Optional[dict]:
        """Lấy snapshot zone mới nhất theo zone_id."""
        for item in self._latest_zone_items.values():
            if item.get("zone_id") == zone_id:
                return item
        return None

    def _mark_zone_fallback_request(self, request: RobotDispatchRequest) -> None:
        """Ghi nhớ zone đã gửi request không có định danh người."""
        if request.event != RobotDispatchEvent.ZONE_OCCUPIED:
            return
        self._zone_fallback_requests.add(_request_zone_identity(request))

    def _should_log_requested_skip(self, global_id: int, zone: Zone) -> bool:
        """Chỉ log skip khi người đã SERVED có lượt occupied mới hoặc xuất hiện ở zone khác."""
        service = self._person_service_states.get(global_id)
        if service is None:
            return True
        zone_identity = _zone_identity(zone)
        if service.zone_id != zone_identity:
            return True
        if zone_identity in self._zones_cleared_after_request:
            return True

        previous_state = self._previous_states.get(zone_identity)
        return previous_state in {None, ZoneState.EMPTY, ZoneState.PENDING_ENTER}

    def _publish_sent_events(self, requests: Sequence[RobotDispatchRequest]) -> None:
        """Publish one websocket event per successfully sent robot request."""
        for request in requests:
            person = _build_request_person(request)

            if request.event == RobotDispatchEvent.ZONE_OCCUPIED:
                if person is not None:
                    self._last_zone_people[_request_zone_identity(request)] = person
                else:
                    self._last_zone_people.pop(_request_zone_identity(request), None)
            elif request.event == RobotDispatchEvent.ZONE_CLEARED:
                person = person or self._last_zone_people.pop(_request_zone_identity(request), None)

            robot_dispatch_events.publish_sent(request, person=person)

    def _log_requested_skip_once(self, global_id: int, zone: Zone) -> None:
        """Log skip SERVED một lần cho mỗi cặp người-zone trong một lượt occupied."""
        zone_identity = _zone_identity(zone)
        key = (global_id, zone_identity)
        if key in self._logged_requested_skips:
            return

        self._logged_requested_skips.add(key)
        LOGGER.warning(
            "Skip robot request: global_id=%s already served | zone_id=%s",
            global_id,
            zone_identity,
        )
        robot_dispatch_events.publish_skipped_already_served(
            global_id=global_id,
            zone=zone,
            existing_request=_build_existing_request_snapshot(
                self._person_service_states.get(global_id)
            ),
        )

    def _clear_logged_skips_for_zone(self, zone_id: str) -> None:
        """Xóa log guard khi zone đã EMPTY để lượt occupied sau có thể log lại."""
        self._logged_requested_skips = {
            key
            for key in self._logged_requested_skips
            if key[1] != zone_id
        }


# ─────────────────────────────────────────────────────────────────────────────
def _zone_identity(zone: Zone) -> str:
    """Lấy định danh zone ổn định cho state nội bộ dispatcher."""
    return str(zone.id or f"{zone.camera_id}:{zone.name}")


# ─────────────────────────────────────────────────────────────────────────────
def _request_zone_identity(request: RobotDispatchRequest) -> str:
    """Lấy định danh zone ổn định từ request nội bộ."""
    return str(request.zone_id or request.zone_name)


# ─────────────────────────────────────────────────────────────────────────────
def _build_zone_snapshot(zone: Zone) -> dict:
    """Chụp trạng thái zone hiện tại thành dict độc lập với object runtime."""
    return {
        "camera_id": zone.camera_id,
        "camera_name": zone.camera_name,
        "zone_id": zone.id,
        "zone_name": zone.name,
        "state": zone.state.value,
        "goal_pose": dict(zone.goal_pose),
    }


# ─────────────────────────────────────────────────────────────────────────────
def _build_event_zone_from_item(
    item: Optional[dict],
    *,
    fallback_zone_id: Optional[str],
    fallback_zone_name: str,
) -> dict:
    """Tạo zone payload cho websocket từ cache dispatcher."""
    if item is None:
        return {
            "camera_id": "",
            "camera_name": "",
            "zone_id": fallback_zone_id,
            "zone_name": fallback_zone_name,
            "state": "",
        }

    return {
        "camera_id": item["camera_id"],
        "camera_name": item["camera_name"],
        "zone_id": item["zone_id"],
        "zone_name": item["zone_name"],
        "state": item["state"],
    }


# ─────────────────────────────────────────────────────────────────────────────
def _build_uart_zone_item(item: dict) -> dict:
    """Tạo item zone theo format detected/cleared cũ."""
    return {
        "camera_id": item["camera_id"],
        "camera_name": item["camera_name"],
        "zone_id": item["zone_id"],
        "zone_name": item["zone_name"],
        "goal_pose": dict(item["goal_pose"]),
    }


# ─────────────────────────────────────────────────────────────────────────────
def _build_request_person(request: RobotDispatchRequest) -> Optional[dict]:
    """Tạo person payload tối thiểu cho robot dispatch websocket."""
    if request.person_global_id is None:
        return None

    person = {
        "global_id": request.person_global_id,
        "track_id": request.metadata.get("track_id"),
        "similarity": request.similarity,
        "reid_status": request.metadata.get("reid_status"),
    }

    return {
        key: value
        for key, value in person.items()
        if value is not None
    }


# ─────────────────────────────────────────────────────────────────────────────
def _build_existing_request_snapshot(
    record: Optional[PersonServiceRecord],
) -> Optional[dict]:
    """Serialize request state that caused an already-requested skip."""
    if record is None:
        return None

    return {
        "request_id": record.request_id,
        "state": record.state.value,
        "zone_id": record.zone_id,
        "updated_at": record.updated_at,
    }


# ─────────────────────────────────────────────────────────────────────────────
def _feedback_global_id(payload: dict) -> Optional[int]:
    """Parse global_id từ feedback robot nếu robot có gửi kèm."""
    raw = payload.get("person_global_id")
    if raw is None:
        raw = payload.get("global_id")
    if raw is None:
        return None

    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
def _optional_string(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


# ─────────────────────────────────────────────────────────────────────────────
def _select_zone_person(
    zone: Zone,
    *,
    detection_frame: Optional[InferenceFrame],
    zone_names: Optional[Sequence[Optional[str]]],
) -> Optional[Detection]:
    """
    Chọn người có global_id phù hợp nhất trong một zone.
    Hiện đang chỉ chọn ra 1 người
    """
    if detection_frame is None or zone_names is None:
        return None

    candidates: List[Detection] = []
    for index, detection in enumerate(detection_frame.detections):
        if index >= len(zone_names):
            break
        if zone_names[index] != zone.name:
            continue
        if detection.global_id is None:
            continue
        candidates.append(detection)

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda detection: (
            detection.similarity if detection.similarity is not None else -1.0,
            detection.confidence,
        ),
    )
