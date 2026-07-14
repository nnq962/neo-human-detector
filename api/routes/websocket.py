import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder

from api.routes.responses import ok
from api.services import runtime as runtime_service
from src.app.runtime_state import runtime_state
from utils import LOGGER


router = APIRouter()
MIN_RUNTIME_STATUS_INTERVAL_SECONDS = 0.2
MAX_RUNTIME_STATUS_INTERVAL_SECONDS = 10.0


# ───────────────────────────────────────────────────────────────────────────
# Gửi dữ liệu bbox/pose runtime lên web preview.
# Payload đã được serialize sẵn một lần lúc publish — mỗi client chỉ send_text,
# không deepcopy/re-encode.
@router.websocket("/ws/runtime/bboxes")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    LOGGER.info("Client connected to /ws/runtime/bboxes")
    last_sequence = None
    try:
        while True:
            latest = runtime_state.get_latest_payload_json()

            if latest is not None:
                sequence, payload_json = latest
                if sequence != last_sequence:
                    await websocket.send_text(payload_json)
                    last_sequence = sequence

            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        LOGGER.info("Client disconnected from /ws/runtime/bboxes")


# ─────────────────────────────────────────────────────────────────────────
# Gửi trạng thái runtime lên web config/dashboard.
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


# ─────────────────────────────────────────────────────────────────────────
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
