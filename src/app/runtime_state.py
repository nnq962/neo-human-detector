"""
Realtime runtime state shared between the detection runtime and API websocket layer.
"""

from __future__ import annotations

import copy
import threading
import time
from typing import Optional, Sequence

import numpy as np

from src.camera_initializer import Camera
from src.detection.datatypes import Detection, InferenceFrame
from src.zones_management import Zone


# ─────────────────────────────────────────────────────────────────────────────
class RuntimeStateStore:
    """Thread-safe in-memory store for the latest runtime realtime payload."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sequence = 0
        self._latest_payload: Optional[dict] = None

    def publish_detection_batch(self, cameras: dict[str, dict]) -> dict:
        """Publish one batch snapshot containing all camera detection payloads."""
        with self._lock:
            self._sequence += 1
            payload = {
                "timestamp": time.time(),
                "sequence": self._sequence,
                "cameras": cameras,
            }
            self._latest_payload = payload
            return copy.deepcopy(payload)

    def get_latest_payload(self) -> Optional[dict]:
        """Return a defensive copy of the latest published payload."""
        with self._lock:
            return copy.deepcopy(self._latest_payload)

    def clear(self) -> None:
        """Clear realtime payload when runtime stops."""
        with self._lock:
            self._latest_payload = None


# ─────────────────────────────────────────────────────────────────────────────
runtime_state = RuntimeStateStore()


# ─────────────────────────────────────────────────────────────────────────────
def build_camera_detection_payload(
    *,
    camera: Camera,
    detection_frame: InferenceFrame,
    timestamp: float,
    zone_names: Sequence[Optional[str]],
) -> dict:
    """Build the JSON-safe detection payload for one camera in a runtime batch."""
    width, height = _resolution_from_frame(detection_frame)
    zones = {
        _zone_payload_key(zone): {
            "id": zone.id,
            "name": zone.name,
            "state": getattr(zone.state, "value", str(zone.state)),
        }
        for zone in camera.zones
    }

    return {
        "camera_id": camera.id,
        "camera_name": camera.name,
        "timestamp": float(timestamp),
        "frame_index": detection_frame.frame_index,
        "resolution": {
            "width": width,
            "height": height,
        },
        "zones": zones,
        "detections": [
            _serialize_detection(
                detection,
                index=index,
                width=width,
                height=height,
                zone_name=zone_names[index] if index < len(zone_names) else None,
            )
            for index, detection in enumerate(detection_frame.detections)
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
def _serialize_detection(
    detection: Detection,
    *,
    index: int,
    width: int,
    height: int,
    zone_name: Optional[str],
) -> dict:
    """Serialize one Detection into the websocket payload format."""
    return {
        "index": index,
        "confidence": float(detection.confidence),
        "class_id": detection.class_id,
        "track_id": detection.track_id,
        "global_id": detection.global_id,
        "similarity": _optional_float(detection.similarity),
        "status": detection.status,
        "zone": zone_name,
        "bbox": {
            "xyxy": [float(value) for value in detection.bbox],
            "xywh_norm": detection.bbox_normalized(width, height),
        },
        "pose": _serialize_pose(detection, width=width, height=height),
    }


# ─────────────────────────────────────────────────────────────────────────────
def _zone_payload_key(zone: Zone) -> str:
    """Return the stable zone key used in realtime payloads."""
    return str(zone.id or zone.name)


# ─────────────────────────────────────────────────────────────────────────────
def _serialize_pose(detection: Detection, *, width: int, height: int) -> Optional[dict]:
    """Serialize pose keypoints in both pixel and normalized coordinates."""
    if detection.keypoints is None:
        return None

    keypoints = np.asarray(detection.keypoints, dtype=np.float32)
    confidences = (
        np.asarray(detection.keypoints_conf, dtype=np.float32)
        if detection.keypoints_conf is not None
        else np.ones((keypoints.shape[0],), dtype=np.float32)
    )

    return {
        "keypoints": [
            [float(x), float(y), float(confidences[index])]
            for index, (x, y) in enumerate(keypoints[:, :2])
        ],
        "keypoints_norm": [
            [
                float(x / width) if width > 0 else 0.0,
                float(y / height) if height > 0 else 0.0,
                float(confidences[index]),
            ]
            for index, (x, y) in enumerate(keypoints[:, :2])
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
def _resolution_from_frame(detection_frame: InferenceFrame) -> tuple[int, int]:
    """Return a positive frame resolution, falling back to 1x1 if absent."""
    if detection_frame.resolution is None:
        return 1, 1

    width, height = detection_frame.resolution
    return max(int(width), 1), max(int(height), 1)


# ─────────────────────────────────────────────────────────────────────────────
def _optional_float(value: Optional[float]) -> Optional[float]:
    """Convert optional numeric values to float without changing None."""
    return float(value) if value is not None else None
