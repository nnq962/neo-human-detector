import time
from typing import Dict, List, Optional, Tuple
import numpy as np
from src.models import Camera, Zone


def build_detection_websocket_payload(
    camera: Camera,
    resolution: Tuple[int, int],
    bboxes: np.ndarray,
    confs: np.ndarray,
    zones: List[Zone],
    zone_counts: Optional[Dict[str, int]] = None,
) -> dict:
    """Đóng gói bbox và trạng thái zone cho WebSocket preview."""
    w, h = resolution
    objects_data = []

    for bbox, conf in zip(bboxes, confs):
        x1, y1, x2, y2 = bbox[:4]
        objects_data.append({
            "bbox": [float(x1 / w), float(y1 / h), float((x2 - x1) / w), float((y2 - y1) / h)],
            "conf": float(conf)
        })

    return {
        "timestamp": int(time.time() * 1000),
        "camera_id": camera.id,
        "camera_name": camera.name,
        "resolution": {"width": w, "height": h},
        "count": len(objects_data),
        "objects": objects_data,
        "zones": {zone.key: zone.state.value for zone in zones},
        "zone_counts": zone_counts or {zone.key: 0 for zone in zones},
    }
