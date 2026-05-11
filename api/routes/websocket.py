import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from api.services.detector import get_latest_ws_payload
from uart.uart_manager import uart_manager
from utils import LOGGER

router = APIRouter()

# ────────────────────────────────────────────────────────────────
# Gửi dữ liệu lên web priview
@router.websocket("/ws/bboxes")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    LOGGER.info("Client connected to /ws/bboxes")
    last_timestamp = 0
    try:
        while True:
            payload = get_latest_ws_payload()
            if payload and payload.get("timestamp") != last_timestamp:
                await websocket.send_json(payload)
                last_timestamp = payload.get("timestamp")
            
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
