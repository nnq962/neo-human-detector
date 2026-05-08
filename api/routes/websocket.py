import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from api.services.websocket import ws_manager
from utils import LOGGER

router = APIRouter()

@router.websocket("/ws/robot")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    LOGGER.info("Client connected to /ws/robot")
    last_timestamp = 0
    try:
        while True:
            payload = ws_manager.latest_payload
            if payload and payload.get("timestamp") != last_timestamp:
                await websocket.send_json(payload)
                last_timestamp = payload.get("timestamp")
            
            # Quét dữ liệu 20 lần mỗi giây (50ms)
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        LOGGER.info("Client disconnected from /ws/robot")
