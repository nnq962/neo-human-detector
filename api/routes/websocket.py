"""Các WebSocket realtime cho màn hình public và dashboard riêng tư."""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder

from api.routes.auth import SESSION_COOKIE_NAME
from api.routes.responses import ok
from api.services import runtime as runtime_service
from api.services.auth import auth_service, is_origin_allowed, load_auth_settings
from api.services.hardware_metrics import hardware_metrics_service
from api.services.robot_heartbeat import robot_heartbeat_service
from src.app.runtime_state import runtime_state
from utils import LOGGER


router = APIRouter()
MIN_RUNTIME_STATUS_INTERVAL_SECONDS = 0.2
MAX_RUNTIME_STATUS_INTERVAL_SECONDS = 10.0
ROBOT_HEARTBEAT_INTERVAL_SECONDS = 1.0
RUNTIME_TASK_INTERVAL_SECONDS = 0.5
DEFAULT_HARDWARE_METRICS_INTERVAL_SECONDS = 1.0


# ─────────────────────────────────────────────────────────────────────────────
async def _require_private_websocket(websocket: WebSocket) -> bool:
    """Xác thực cookie và Origin trước khi chấp nhận WebSocket riêng tư."""
    settings = load_auth_settings()
    if not settings.enabled:
        return True

    host = websocket.headers.get("host", "")
    scheme = "https" if websocket.url.scheme == "wss" else "http"
    if not is_origin_allowed(
        websocket.headers.get("origin"),
        scheme=scheme,
        host=host,
    ):
        await websocket.accept()
        await websocket.close(code=4403, reason="Origin không được phép.")
        return False

    token = websocket.cookies.get(SESSION_COOKIE_NAME)
    if not settings.password or not auth_service.is_session_valid(token):
        await websocket.accept()
        await websocket.close(code=4401, reason="Phiên đăng nhập không hợp lệ.")
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
async def _serve_bboxes(websocket: WebSocket) -> None:
    """Phát payload bbox mới nhất cho một WebSocket đã được cho phép."""
    await websocket.accept()
    LOGGER.info("Client connected to %s", websocket.url.path)
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
        LOGGER.info("Client disconnected from %s", websocket.url.path)


# ─────────────────────────────────────────────────────────────────────────────
@router.websocket("/ws/runtime/bboxes")
async def private_bboxes_websocket(websocket: WebSocket) -> None:
    """Phát bbox cho dashboard sau khi kiểm tra session."""
    if await _require_private_websocket(websocket):
        await _serve_bboxes(websocket)


# ─────────────────────────────────────────────────────────────────────────────
@router.websocket("/ws/public/runtime/bboxes")
async def public_bboxes_websocket(websocket: WebSocket) -> None:
    """Phát bbox công khai cho màn hình live."""
    await _serve_bboxes(websocket)


# ─────────────────────────────────────────────────────────────────────────────
@router.websocket("/ws/runtime/status")
async def runtime_status_websocket(websocket: WebSocket) -> None:
    """Phát trạng thái runtime định kỳ cho dashboard riêng tư."""
    if not await _require_private_websocket(websocket):
        return

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


# ─────────────────────────────────────────────────────────────────────────────
async def _serve_robot_heartbeats(websocket: WebSocket) -> None:
    """Phát snapshot robot cho một WebSocket đã được cho phép."""
    await websocket.accept()
    LOGGER.info("Client connected to %s", websocket.url.path)

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
        LOGGER.info("Client disconnected from %s", websocket.url.path)


# ─────────────────────────────────────────────────────────────────────────────
@router.websocket("/ws/uart/robots")
async def uart_robots_websocket(websocket: WebSocket) -> None:
    """Phát vị trí robot cho dashboard sau khi kiểm tra session."""
    if await _require_private_websocket(websocket):
        await _serve_robot_heartbeats(websocket)


# ─────────────────────────────────────────────────────────────────────────────
@router.websocket("/ws/public/uart/robots")
async def public_uart_robots_websocket(websocket: WebSocket) -> None:
    """Phát vị trí robot công khai cho overlay trang live."""
    await _serve_robot_heartbeats(websocket)


# ─────────────────────────────────────────────────────────────────────────────
@router.websocket("/ws/runtime/tasks")
async def runtime_tasks_websocket(websocket: WebSocket) -> None:
    """Phát snapshot task runtime định kỳ tới dashboard riêng tư."""
    if not await _require_private_websocket(websocket):
        return

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
@router.websocket("/ws/metrics")
async def hardware_metrics_websocket(websocket: WebSocket) -> None:
    """Phát snapshot tài nguyên phần cứng tới dashboard riêng tư."""
    if not await _require_private_websocket(websocket):
        return

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


# ─────────────────────────────────────────────────────────────────────────────
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
