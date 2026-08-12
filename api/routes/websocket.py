import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder

from api.routes.responses import ok
from api.services.hardware_metrics import hardware_metrics_service
from api.services import runtime as runtime_service
from api.services.robot_heartbeat import robot_heartbeat_service
from src.app.runtime_state import runtime_state
from utils import LOGGER


router = APIRouter()
MIN_RUNTIME_STATUS_INTERVAL_SECONDS = 0.2
MAX_RUNTIME_STATUS_INTERVAL_SECONDS = 10.0
ROBOT_HEARTBEAT_INTERVAL_SECONDS = 1.0
RUNTIME_TASK_INTERVAL_SECONDS = 0.5
DEFAULT_HARDWARE_METRICS_INTERVAL_SECONDS = 1.0


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
# Gửi snapshot robot mới nhất và tự cập nhật trạng thái online/offline.
@router.websocket("/ws/uart/robots")
async def uart_robots_websocket(websocket: WebSocket):
    await websocket.accept()
    LOGGER.info("Client connected to /ws/uart/robots")

    try:
        while True:
            await websocket.send_json(
                jsonable_encoder(
                    ok(
                        "Robot heartbeat snapshots loaded successfully.",
                        robot_heartbeat_service.snapshot(),
                    )
                )
            )
            await asyncio.sleep(ROBOT_HEARTBEAT_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        LOGGER.info("Client disconnected from /ws/uart/robots")


# ─────────────────────────────────────────────────────────────────────────────
# Gửi read-model task của phiên runtime hiện tại.
@router.websocket("/ws/runtime/tasks")
async def runtime_tasks_websocket(websocket: WebSocket):
    """Phát snapshot task runtime định kỳ tới WebSocket client."""
    await websocket.accept()
    LOGGER.info("Client connected to /ws/runtime/tasks")

    try:
        while True:
            await websocket.send_json(
                jsonable_encoder(
                    ok(
                        "Runtime task snapshot loaded successfully.",
                        runtime_service.get_runtime_tasks(),
                    )
                )
            )
            await asyncio.sleep(RUNTIME_TASK_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        LOGGER.info("Client disconnected from /ws/runtime/tasks")


# ─────────────────────────────────────────────────────────────────────────────
# Gửi snapshot CPU, RAM và GPU để hiển thị giám sát phần cứng.
@router.websocket("/ws/metrics")
async def hardware_metrics_websocket(websocket: WebSocket):
    """Phát snapshot tài nguyên phần cứng định kỳ tới WebSocket client."""
    await websocket.accept()
    interval_seconds = _hardware_metrics_interval_from_websocket(websocket)
    LOGGER.info("Client connected to /ws/metrics")

    try:
        while True:
            await websocket.send_json(
                jsonable_encoder(
                    ok(
                        "Hardware metrics loaded successfully.",
                        hardware_metrics_service.snapshot(),
                    )
                )
            )
            await asyncio.sleep(interval_seconds)
    except WebSocketDisconnect:
        LOGGER.info("Client disconnected from /ws/metrics")


# ─────────────────────────────────────────────────────────────────────────
def _runtime_status_interval_from_websocket(websocket: WebSocket) -> float:
    """Đọc khoảng gửi trạng thái runtime từ query parameter của WebSocket."""
    return _interval_from_websocket(websocket, default=1.0)


# ─────────────────────────────────────────────────────────────────────────────
def _hardware_metrics_interval_from_websocket(websocket: WebSocket) -> float:
    """Đọc khoảng gửi metrics phần cứng từ query parameter của WebSocket."""
    return _interval_from_websocket(
        websocket,
        default=DEFAULT_HARDWARE_METRICS_INTERVAL_SECONDS,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _interval_from_websocket(websocket: WebSocket, *, default: float) -> float:
    """Chuẩn hóa query ``interval`` vào khoảng polling WebSocket cho phép."""
    raw_interval = websocket.query_params.get("interval")

    try:
        interval_seconds = float(raw_interval) if raw_interval is not None else default
    except ValueError:
        interval_seconds = default

    return min(
        max(interval_seconds, MIN_RUNTIME_STATUS_INTERVAL_SECONDS),
        MAX_RUNTIME_STATUS_INTERVAL_SECONDS,
    )
