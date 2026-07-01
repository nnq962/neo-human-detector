import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from api.routes.responses import ok
from api.services import runtime as runtime_service
from src.app.runtime_state import runtime_state
from src.robot_dispatch.event_store import robot_dispatch_events
from uart.uart_manager import uart_manager
from utils import LOGGER

router = APIRouter()
MIN_RUNTIME_STATUS_INTERVAL_SECONDS = 0.2
MAX_RUNTIME_STATUS_INTERVAL_SECONDS = 10.0


def get_latest_bbox_payload():
    return runtime_state.get_latest_payload()

# ────────────────────────────────────────────────────────────────
# Gửi dữ liệu bbox/pose runtime lên web preview
@router.websocket("/ws/runtime/bboxes")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    LOGGER.info("Client connected to /ws/runtime/bboxes")
    last_sequence = None
    try:
        while True:
            payload = get_latest_bbox_payload()
            sequence = payload.get("sequence") if payload else None

            if payload and sequence != last_sequence:
                await websocket.send_json(payload)
                last_sequence = sequence
            
            # Quét dữ liệu 20 lần mỗi giây (50ms)
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        LOGGER.info("Client disconnected from /ws/runtime/bboxes")

# ────────────────────────────────────────────────────────────────
# Chuyển toàn bộ event UART receive lên web config/debug.
@router.websocket("/ws/uart/events")
async def uart_events_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    event_type = _normalize_uart_event_type(websocket.query_params.get("type"))
    prefix = websocket.query_params.get("prefix")

    if event_type == "invalid":
        await websocket.close(code=1008, reason="Invalid UART event type filter.")
        return

    last_sequence = uart_manager.get_event_sequence()
    LOGGER.info("Client connected to /ws/uart/events")
    try:
        while True:
            events = uart_manager.get_events_after(last_sequence)
            for event in events:
                last_sequence = event["sequence"]
                if _matches_uart_event_filter(event, event_type, prefix):
                    await websocket.send_json(event)

            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        LOGGER.info("Client disconnected from /ws/uart/events")

# ────────────────────────────────────────────────────────────────
# Chuyển event robot dispatch lên web dashboard/debug.
@router.websocket("/ws/robot-dispatch/events")
async def robot_dispatch_events_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    last_sequence = robot_dispatch_events.get_event_sequence()
    LOGGER.info("Client connected to /ws/robot-dispatch/events")
    try:
        while True:
            events = robot_dispatch_events.get_events_after(last_sequence)
            for event in events:
                last_sequence = event["sequence"]
                await websocket.send_json(event)

            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        LOGGER.info("Client disconnected from /ws/robot-dispatch/events")

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


def _normalize_uart_event_type(raw_event_type: str | None) -> str | None:
    if raw_event_type is None or raw_event_type == "" or raw_event_type == "all":
        return None

    if raw_event_type in {"json", "string"}:
        return raw_event_type

    return "invalid"


def _matches_uart_event_filter(
    event: dict,
    event_type: str | None,
    prefix: str | None,
) -> bool:
    if event_type is not None and event.get("type") != event_type:
        return False

    if prefix is not None and not str(event.get("raw", "")).startswith(prefix):
        return False

    return True
