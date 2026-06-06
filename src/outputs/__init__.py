"""
Module outputs gom các adapter đưa dữ liệu pipeline ra bên ngoài.

Các output hiện có:
- WebSocket payload cho frontend preview.
- Visualization overlay để debug bằng OpenCV.

UART vẫn đang nằm ở package `uart/` vì đó là integration phần cứng riêng.
"""

from src.outputs.visualization import draw_detection_overlay, draw_legacy_overlay, draw_zones
from src.outputs.websocket_payload import (
    build_detection_websocket_payload,
    build_legacy_detection_websocket_payload,
)

__all__ = [
    "build_detection_websocket_payload",
    "build_legacy_detection_websocket_payload",
    "draw_detection_overlay",
    "draw_legacy_overlay",
    "draw_zones",
]
