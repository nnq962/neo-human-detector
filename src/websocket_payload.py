import time
from typing import List
import numpy as np
from src.models import Zone


def build_detection_websocket_payload(
    frame: np.ndarray,
    bboxes: np.ndarray,
    confs: np.ndarray,
    zones: List[Zone],
) -> dict:
    """Đóng gói bbox và trạng thái zone cho WebSocket preview."""
    h, w = frame.shape[:2]
    objects_data = []

    for bbox, conf in zip(bboxes, confs):
        x1, y1, x2, y2 = bbox[:4]
        objects_data.append({
            "bbox": [float(x1 / w), float(y1 / h), float((x2 - x1) / w), float((y2 - y1) / h)],
            "conf": float(conf)
        })

    return {
        "timestamp": int(time.time() * 1000),
        "resolution": {"width": w, "height": h},
        "count": len(objects_data),
        "objects": objects_data,
        "zones": {zone.name: zone.state.value for zone in zones}
    }
