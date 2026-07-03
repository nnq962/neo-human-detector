"""
Realtime runtime state shared between the detection runtime and API websocket layer.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Optional, Sequence

import numpy as np

from src.camera_initializer import Camera
from src.detection.datatypes import Detection, InferenceFrame
from src.zones_management import Zone


# ─────────────────────────────────────────────────────────────────────────────
class RuntimeStateStore:
    """Thread-safe in-memory store for the latest runtime realtime payload.

    The payload is serialized to JSON once at publish time so websocket
    handlers can fan it out to every client without re-encoding or copying.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sequence = 0
        self._latest_json: Optional[str] = None

    def publish_detection_batch(self, cameras: dict[str, dict]) -> None:
        """Publish one batch snapshot containing all camera detection payloads."""
        with self._lock:
            self._sequence += 1
            payload = {
                "timestamp": time.time(),
                "sequence": self._sequence,
                "cameras": cameras,
            }
            self._latest_json = json.dumps(payload, separators=(",", ":"))

    def get_latest_payload_json(self) -> Optional[tuple[int, str]]:
        """Return (sequence, pre-serialized JSON) of the latest payload."""
        with self._lock:
            if self._latest_json is None:
                return None
            return self._sequence, self._latest_json

    def clear(self) -> None:
        """Clear realtime payload when runtime stops."""
        with self._lock:
            self._sequence += 1
            payload = {
                "timestamp": time.time(),
                "sequence": self._sequence,
                "cameras": {},
            }
            self._latest_json = json.dumps(payload, separators=(",", ":"))


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
        },
        "pose": _serialize_pose(detection),
    }


# ─────────────────────────────────────────────────────────────────────────────
def _zone_payload_key(zone: Zone) -> str:
    """Return the stable zone key used in realtime payloads."""
    return str(zone.id or zone.name)


# ─────────────────────────────────────────────────────────────────────────────
def _serialize_pose(detection: Detection) -> Optional[dict]:
    """Serialize pose keypoints in pixel coordinates."""
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
