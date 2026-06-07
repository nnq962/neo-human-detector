"""
Builder payload WebSocket cho frontend preview.

File này chỉ làm nhiệm vụ format dữ liệu sang JSON-serializable dict.
Nó không đọc camera stream, không chạy detector, và không tự gửi WebSocket.
"""

import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from src.detection.detections import Detection, DetectionFrame
from src.zones.models import Zone


# ─────────────────────────────────────────────────────────────────────────────
def build_detection_websocket_payload(
    *,
    camera: Any,
    detection_frame: DetectionFrame,
    zones: Sequence[Zone],
    zone_counts: Optional[Mapping[str, int]] = None,
) -> Dict[str, Any]:
    """
    Đóng gói detection frame và trạng thái zone cho `/ws/bboxes`.

    `camera` chỉ cần có field/property `id` và `name`, nên dùng được với cả
    `src.models.Camera` cũ lẫn `src.camera.models.Camera` mới.
    """
    resolution = _resolve_payload_resolution(detection_frame)

    return _build_payload_dict(
        camera_id=str(camera.id),
        camera_name=str(camera.name),
        resolution=resolution,
        objects=_build_detection_objects(detection_frame.detections, resolution),
        zones=zones,
        zone_counts=zone_counts,
        timestamp_ms=_current_timestamp_ms(),
    )


# ─────────────────────────────────────────────────────────────────────────────
def build_legacy_detection_websocket_payload(
    *,
    camera: Any,
    resolution: Tuple[int, int],
    bboxes: np.ndarray,
    confs: np.ndarray,
    zones: Sequence[Zone],
    zone_counts: Optional[Mapping[str, int]] = None,
) -> Dict[str, Any]:
    """
    Adapter tạm cho pipeline cũ đang dùng numpy `bboxes/confs`.

    Khi runtime đã chuyển hẳn sang `DetectionFrame`, hàm này có thể bỏ.
    """
    detections = _detections_from_arrays(bboxes, confs)

    return _build_payload_dict(
        camera_id=str(camera.id),
        camera_name=str(camera.name),
        resolution=resolution,
        objects=_build_detection_objects(detections, resolution),
        zones=zones,
        zone_counts=zone_counts,
        timestamp_ms=_current_timestamp_ms(),
    )


# ─────────────────────────────────────────────────────────────────────────────
def _build_payload_dict(
    *,
    camera_id: str,
    camera_name: str,
    resolution: Tuple[int, int],
    objects: List[Dict[str, Any]],
    zones: Sequence[Zone],
    zone_counts: Optional[Mapping[str, int]],
    timestamp_ms: int,
) -> Dict[str, Any]:
    """Tạo dict payload cuối cùng theo contract frontend đang đọc."""
    width, height = resolution

    return {
        "timestamp": timestamp_ms,
        "camera_id": camera_id,
        "camera_name": camera_name,
        "resolution": {"width": width, "height": height},
        "count": len(objects),
        "objects": objects,
        "zones": {zone.key: zone.state.value for zone in zones},
        "zone_counts": dict(zone_counts) if zone_counts is not None else _empty_zone_counts(zones),
    }


# ─────────────────────────────────────────────────────────────────────────────
def _build_detection_objects(
    detections: Sequence[Detection],
    resolution: Tuple[int, int],
) -> List[Dict[str, Any]]:
    """Chuyển danh sách Detection thành object nhỏ cho frontend canvas."""
    width, height = resolution
    objects: List[Dict[str, Any]] = []

    if width <= 0 or height <= 0:
        return objects

    for detection in detections:
        item: Dict[str, Any] = {
            "bbox": detection.to_xywh_normalized(width, height),
            "conf": detection.confidence,
        }

        # ByteTrack id chỉ xuất hiện khi chạy `YoloDetector.track_stream()`.
        if detection.track_id is not None:
            item["track_id"] = detection.track_id

        if detection.class_id is not None:
            item["class_id"] = detection.class_id

        if detection.label:
            item["label"] = detection.label

        objects.append(item)

    return objects


# ─────────────────────────────────────────────────────────────────────────────
def _detections_from_arrays(bboxes: np.ndarray, confs: np.ndarray) -> List[Detection]:
    """Chuyển dữ liệu numpy cũ sang Detection chuẩn."""
    detections: List[Detection] = []

    for bbox, conf in zip(bboxes, confs):
        if not np.isfinite(bbox[:4]).all() or not np.isfinite(conf):
            continue

        x1, y1, x2, y2 = bbox[:4]
        if x2 <= x1 or y2 <= y1:
            continue

        detections.append(
            Detection(
                bbox=(float(x1), float(y1), float(x2), float(y2)),
                confidence=float(conf),
            )
        )

    return detections


# ─────────────────────────────────────────────────────────────────────────────
def _resolve_payload_resolution(detection_frame: DetectionFrame) -> Tuple[int, int]:
    """Lấy resolution từ DetectionFrame, fallback về (0, 0) nếu chưa có."""
    if detection_frame.resolution is None:
        return 0, 0

    width, height = detection_frame.resolution
    return int(width), int(height)


# ─────────────────────────────────────────────────────────────────────────────
def _empty_zone_counts(zones: Sequence[Zone]) -> Dict[str, int]:
    """Tạo bộ đếm 0 cho tất cả zone khi state machine chưa trả zone_counts."""
    return {zone.key: 0 for zone in zones}


# ─────────────────────────────────────────────────────────────────────────────
def _current_timestamp_ms() -> int:
    """Timestamp milliseconds để frontend biết frame nào mới hơn."""
    return int(time.time() * 1000)
