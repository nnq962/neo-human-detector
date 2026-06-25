import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from api.routes.responses import ok
from api.services import runtime as runtime_service
from uart.uart_manager import uart_manager
from utils import LOGGER

router = APIRouter()
MIN_RUNTIME_STATUS_INTERVAL_SECONDS = 0.2
MAX_RUNTIME_STATUS_INTERVAL_SECONDS = 10.0


def get_latest_bbox_payload():
    return None

# ────────────────────────────────────────────────────────────────
# Gửi dữ liệu lên web priview
@router.websocket("/ws/bboxes")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    LOGGER.info("Client connected to /ws/bboxes")
    last_camera_timestamps = {}
    try:
        while True:
            payload = get_latest_bbox_payload()
            cameras = payload.get("cameras", {}) if payload else {}
            camera_timestamps = {
                camera_id: camera_payload.get("timestamp")
                for camera_id, camera_payload in cameras.items()
                if isinstance(camera_payload, dict) and camera_payload.get("timestamp") is not None
            }

            if camera_timestamps and camera_timestamps != last_camera_timestamps:
                await websocket.send_json(payload)
                last_camera_timestamps = camera_timestamps
            
            # Quét dữ liệu 20 lần mỗi giây (50ms)
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        LOGGER.info("Client disconnected from /ws/bboxes")

# ────────────────────────────────────────────────────────────────
# Chuyển dữ liệu từ uart receive lên web config
@router.websocket("/ws/uart")
async def uart_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    last_timestamp = 0
    LOGGER.info("Client connected to /ws/uart")
    try:
        while True:
            payload = uart_manager.latest_received_data
            if payload and payload.get("timestamp") != last_timestamp:
                await websocket.send_json(payload["payload"])
                last_timestamp = payload.get("timestamp")
            
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        LOGGER.info("Client disconnected from /ws/uart")

# ────────────────────────────────────────────────────────────────
# Gửi trạng thái runtime lên web config/dashboard
@router.websocket("/ws/runtime/status")
async def runtime_status_websocket(websocket: WebSocket):
    await websocket.accept()
    interval_seconds = _runtime_status_interval_from_websocket(websocket)
    LOGGER.info("Client connected to /ws/runtime/status")

    try:
        while True:
            await websocket.send_json(
                jsonable_encoder(
                    ok(
                        "Runtime status loaded successfully.",
                        runtime_service.get_runtime_status(),
                    )
                )
            )
            await asyncio.sleep(interval_seconds)
    except WebSocketDisconnect:
        LOGGER.info("Client disconnected from /ws/runtime/status")


def _runtime_status_interval_from_websocket(websocket: WebSocket) -> float:
    raw_interval = websocket.query_params.get("interval")

    try:
        interval_seconds = float(raw_interval) if raw_interval is not None else 1.0
    except ValueError:
        interval_seconds = 1.0

    return min(
        max(interval_seconds, MIN_RUNTIME_STATUS_INTERVAL_SECONDS),
        MAX_RUNTIME_STATUS_INTERVAL_SECONDS,
    )
