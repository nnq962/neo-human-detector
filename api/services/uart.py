from fastapi import HTTPException, status

from api.models.uart import (
    UartConfig,
    UartConfigUpdate,
    UartMessageRequest,
    UartMoveToPointRequest,
)
from api.services import config_store
from api.services.manual_robot_task import (
    manual_robot_task_service,
    robot_uart_operation_lock,
)
from api.services.robot_move import (
    RobotMoveBusyError,
    RobotMoveUnavailableError,
    robot_move_registry,
)
from src.robot_dispatch_v2.datatypes import (
    AckReasonCode,
    AckResultCode,
    MoveToPoint,
)
from uart_v2.uart_manager import uart_manager_v2


# ─────────────────────────────────────────────────────────────────────────────
def _model_dump(model, **kwargs) -> dict:
    """Chuyển Pydantic model thành dictionary với các tùy chọn đã nhận."""
    return model.model_dump(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
def _normalize_uart_config(config: dict) -> dict:
    """Chuẩn hóa section cấu hình UART bằng model Pydantic."""
    return UartConfig(
        port=config.get("port", "/dev/ttyS4"),
        baudrate=config.get("baudrate", 115200),
    ).model_dump()


# ─────────────────────────────────────────────────────────────────────────────
def get_uart_config() -> dict:
    """Đọc và trả cấu hình UART hiện hành."""
    config = config_store.get_config_data()

    return _normalize_uart_config(config.get("uart", {}))


# ─────────────────────────────────────────────────────────────────────────────
def get_uart_status() -> dict:
    """Trả trạng thái kết nối UART và các task thủ công hiện tại."""
    uart_status = uart_manager_v2.status()
    return {
        "protocol": "v2",
        "port": uart_status["port"],
        "baudrate": uart_status["baudrate"],
        "timeout": uart_status["timeout"],
        "connected": uart_status["connected"],
        "listening": uart_status["is_listening"],
        "last_connected_at": uart_status["last_connected_at"],
        "last_disconnected_at": uart_status["last_disconnected_at"],
        "last_received_at": uart_status["last_received_at"],
        "last_error": uart_status["last_error"],
        "manual_tasks": manual_robot_task_service.snapshot(),
    }


# ─────────────────────────────────────────────────────────────────────────────
def get_robot_snapshots() -> dict:
    """Trả trạng thái robot mới nhất được tổng hợp từ Heartbeat UART."""
    from api.services.robot_heartbeat import robot_heartbeat_service

    return robot_heartbeat_service.snapshot()


# ─────────────────────────────────────────────────────────────────────────────
def update_uart_config(update: UartConfigUpdate) -> dict:
    """Cập nhật UART an toàn rồi kết nối lại với tham số mới."""
    update_data = _model_dump(update, exclude_none=True, exclude_unset=True)

    if update_data:
        with robot_uart_operation_lock:
            _ensure_uart_reconfigure_is_safe()

            def mutate(config: dict) -> dict:
                """Ghi các trường UART mới vào cấu hình gốc."""
                uart_config = config.setdefault("uart", {})
                uart_config.update(update_data)
                uart_config = _normalize_uart_config(uart_config)
                config["uart"] = uart_config
                return uart_config

            uart_config = config_store.update_config_data(mutate)
            connected = uart_manager_v2.reconfigure(
                port=uart_config["port"],
                baudrate=uart_config["baudrate"],
            )
            if not connected:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Could not connect UART V2 with the updated configuration.",
                )
            return uart_config

    return get_uart_config()


# ─────────────────────────────────────────────────────────────────────────────
def send_uart_message(request: UartMessageRequest) -> dict:
    """Gửi message điều khiển thủ công khi vision Runtime không hoạt động."""
    from api.services.runtime import get_runtime_status

    with robot_uart_operation_lock:
        runtime_status = get_runtime_status()
        if runtime_status["thread_alive"] or runtime_status["state"] in {
            "starting",
            "stopping",
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Manual UART messages are not allowed while Runtime is running.",
            )

        config = config_store.get_config_data().get("robot_dispatch", {})
        ack_timeout_seconds = float(config.get("ack_timeout_seconds", 1.0))
        max_retries = int(config.get("max_retries", 10))

        if isinstance(request, UartMoveToPointRequest):
            return _send_move_to_point(
                request,
                ack_timeout_seconds=ack_timeout_seconds,
                max_retries=max_retries,
            )

        return manual_robot_task_service.send(
            request,
            ack_timeout_seconds=ack_timeout_seconds,
            max_retries=max_retries,
        )


# ─────────────────────────────────────────────────────────────────────────────
def send_move_to_point(request: UartMoveToPointRequest) -> dict:
    """Gửi lệnh MoveToPoint qua API chuyên dụng."""
    return send_uart_message(request)


# ─────────────────────────────────────────────────────────────────────────────
def _send_move_to_point(
    request: UartMoveToPointRequest,
    *,
    ack_timeout_seconds: float,
    max_retries: int,
) -> dict:
    """Gửi MoveToPoint và chỉ báo thành công khi robot chấp nhận lệnh."""
    if not uart_manager_v2.is_connected():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="UART V2 is not connected.",
        )

    from api.services.robot_heartbeat import robot_heartbeat_service

    try:
        reservation = robot_move_registry.reserve(
            request.robot_id,
            robot_heartbeat_service.state_store,
        )
    except RobotMoveUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except RobotMoveBusyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    message = MoveToPoint(
        robot_id=request.robot_id,
        move_id=reservation.move_id,
        x=request.x,
        y=request.y,
        theta=request.theta,
    )
    try:
        ack = uart_manager_v2.send_with_retry_ack(
            message,
            reference_id=reservation.move_id,
            timeout=ack_timeout_seconds,
            max_retries=max_retries,
        )
    except Exception:
        robot_move_registry.mark_uncertain(reservation)
        raise
    if ack is None:
        robot_move_registry.mark_uncertain(reservation)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Không nhận được ACK cho lệnh MoveToPoint.",
        )
    if ack.result_code != AckResultCode.ACCEPTED:
        robot_move_registry.mark_rejected(
            reservation,
            robot_busy=ack.reason_code == AckReasonCode.ROBOT_BUSY,
        )
        reason_name = _ack_reason_name(ack.reason_code)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Robot từ chối lệnh MoveToPoint: "
                f"{reason_name} (reason_code={ack.reason_code})."
            ),
        )

    robot_move_registry.mark_accepted(reservation)

    return {
        "message_type": request.message_type,
        "robot_id": request.robot_id,
        "move_id": reservation.move_id,
        "acknowledged": True,
        "ack": {
            "result_code": int(ack.result_code),
            "result": AckResultCode(ack.result_code).name,
            "reason_code": int(ack.reason_code),
            "reason": _ack_reason_name(ack.reason_code),
        },
        "target": {
            "x": request.x,
            "y": request.y,
            "theta": request.theta,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
def _ack_reason_name(reason_code: int) -> str:
    """Đổi mã nguyên nhân ACK sang tên enum, có fallback cho mã lạ."""
    try:
        return AckReasonCode(reason_code).name
    except ValueError:
        return "UNKNOWN"


# ─────────────────────────────────────────────────────────────────────────────
def _ensure_uart_reconfigure_is_safe() -> None:
    """Chặn reconnect khi Runtime hoặc task thủ công đang dùng UART."""
    from api.services.runtime import get_runtime_status

    runtime_status = get_runtime_status()
    if runtime_status["thread_alive"] or runtime_status["state"] in {
        "starting",
        "stopping",
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="UART configuration cannot change while Runtime is running.",
        )

    if manual_robot_task_service.has_active_tasks():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="UART configuration cannot change while a manual task is active.",
        )

    from api.services.robot_heartbeat import robot_heartbeat_service

    if robot_move_registry.has_any_active_move(
        robot_heartbeat_service.state_store
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="UART configuration cannot change while a robot move is active.",
        )
