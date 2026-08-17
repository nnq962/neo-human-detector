from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError

from api.models.uart import (
    UartMessageRequest,
    UartMoveToPointRequest,
    UartTaskAssignRequest,
    UartTaskCancelRequest,
)
from api.services.manual_robot_task import ManualRobotTaskService
from api.services.robot_move import RobotMoveRegistry
from api.services.runtime import RuntimeManager
from api.services import uart as uart_service
from src.robot_dispatch_v2.datatypes import (
    Ack,
    AckReasonCode,
    AckResultCode,
    Heartbeat,
    MessageType,
    MoveToPoint,
    RobotStateCode,
    TaskAssign,
    TaskCancel,
    TaskStatus,
    TaskStatusCode,
)
from src.robot_dispatch_v2.robot_state import RobotStateStore


# ─────────────────────────────────────────────────────────────────────────────
class FakeManualUart:
    """UART V2 giả để test manual task mà không mở serial."""

    def __init__(self) -> None:
        """Khởi tạo UART giả với hàng đợi kết quả có thể điều khiển."""
        self.connected = True
        self.handlers = {}
        self.sent = []
        self.retry_outcomes = []
        self.retry_acks = []
        self.retry_references = []

    # ─────────────────────────────────────────────────────────────────────────
    def add_handler(self, message_type, handler) -> None:
        """Đăng ký handler giả theo loại message."""
        self.handlers[int(message_type)] = handler

    # ─────────────────────────────────────────────────────────────────────────
    def remove_handler(self, message_type, handler) -> None:
        """Gỡ handler khi đúng instance đang được đăng ký."""
        if self.handlers.get(int(message_type)) == handler:
            self.handlers.pop(int(message_type))

    # ─────────────────────────────────────────────────────────────────────────
    def send_message(self, message) -> bool:
        """Lưu message gửi thường và giả lập thành công."""
        self.sent.append(message)
        return True

    # ─────────────────────────────────────────────────────────────────────────
    def send_with_retry(
        self,
        message,
        reference_id,
        timeout=1.0,
        max_retries=5,
    ) -> bool:
        """Lưu message và trả kết quả ACK boolean đã xếp hàng."""
        self.sent.append(message)
        self.retry_references.append(reference_id)
        if self.retry_outcomes:
            return self.retry_outcomes.pop(0)
        return True

    # ─────────────────────────────────────────────────────────────────────────
    def send_with_retry_ack(
        self,
        message,
        reference_id,
        timeout=1.0,
        max_retries=5,
    ):
        """Giả lập gửi message và trả ACK đầy đủ cho API MoveToPoint."""
        self.sent.append(message)
        self.retry_references.append(reference_id)
        if self.retry_acks:
            return self.retry_acks.pop(0)
        return Ack(
            robot_id=message.robot_id,
            acked_type=message.MESSAGE_TYPE,
            reference_id=reference_id,
            result_code=AckResultCode.ACCEPTED,
            reason_code=AckReasonCode.NONE,
        )

    # ─────────────────────────────────────────────────────────────────────────
    def is_connected(self) -> bool:
        """Trả trạng thái kết nối UART giả."""
        return self.connected

    # ─────────────────────────────────────────────────────────────────────────
    def emit(self, message) -> None:
        """Phát một message nhận vào handler tương ứng."""
        handler = self.handlers.get(int(message.MESSAGE_TYPE))
        if handler is not None:
            handler(message)


# ─────────────────────────────────────────────────────────────────────────────
def _assign_request(task_id: int = 10) -> UartTaskAssignRequest:
    """Tạo request TaskAssign hợp lệ dùng chung cho test."""
    return UartTaskAssignRequest(
        message_type="task_assign",
        robot_id=1,
        task_id=task_id,
        x=1.5,
        y=2.0,
        theta=0.25,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _move_request() -> UartMoveToPointRequest:
    """Tạo request MoveToPoint hợp lệ dùng chung cho các test."""
    return UartMoveToPointRequest(
        robot_id=1,
        x=1.5,
        y=2.0,
        theta=0.25,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _idle_robot_store() -> RobotStateStore:
    """Tạo state store có robot #1 online và đang IDLE."""
    state_store = RobotStateStore()
    state_store.update_from_heartbeat(
        Heartbeat(
            robot_id=1,
            timestamp=1,
            x=0.0,
            y=0.0,
            theta=0.0,
            state_code=RobotStateCode.IDLE,
        )
    )
    return state_store


# ─────────────────────────────────────────────────────────────────────────────
def test_manual_assign_tracks_status_and_acknowledges_task_status() -> None:
    """Kiểm tra task thủ công được theo dõi và ACK TaskStatus hoàn tất."""
    uart = FakeManualUart()
    service = ManualRobotTaskService(uart)
    service.register_uart_handlers()

    result = service.send(
        _assign_request(),
        ack_timeout_seconds=0.5,
        max_retries=2,
    )

    assert result["acknowledged"]
    assert result["ack"]["result"] == "ACCEPTED"
    assert result["ack"]["reason"] == "NONE"
    assert result["task"]["state"] == "assigned"
    assert isinstance(uart.sent[0], TaskAssign)
    assert service.has_active_tasks()

    uart.emit(
        TaskStatus(
            robot_id=1,
            task_id=10,
            status_code=TaskStatusCode.COMPLETED,
        )
    )

    assert service.snapshot()[0]["state"] == "completed"
    assert not service.has_active_tasks()
    assert isinstance(uart.sent[-1], Ack)
    assert uart.sent[-1].acked_type == MessageType.TASK_STATUS


# ─────────────────────────────────────────────────────────────────────────────
def test_manual_assign_exposes_rejected_ack_reason() -> None:
    """Kiểm tra TaskAssign thủ công trả nguyên nhân khi robot từ chối."""
    uart = FakeManualUart()
    uart.retry_acks = [
        Ack(
            robot_id=1,
            acked_type=MessageType.TASK_ASSIGN,
            reference_id=10,
            result_code=AckResultCode.REJECTED,
            reason_code=AckReasonCode.ROBOT_ERROR,
        )
    ]
    service = ManualRobotTaskService(uart)

    try:
        service.send(
            _assign_request(),
            ack_timeout_seconds=0.5,
            max_retries=2,
        )
    except HTTPException as exc:
        assert exc.status_code == 409
        assert "ROBOT_ERROR" in exc.detail
        assert "reason_code=2" in exc.detail
    else:
        raise AssertionError("TaskAssign bị từ chối phải trả chi tiết ACK")

    assert service.snapshot() == []


# ─────────────────────────────────────────────────────────────────────────────
def test_manual_cancel_requires_and_finishes_active_task() -> None:
    """Kiểm tra TaskCancel kết thúc task thủ công đang hoạt động."""
    uart = FakeManualUart()
    service = ManualRobotTaskService(uart)
    service.send(_assign_request(), ack_timeout_seconds=0.5, max_retries=2)

    result = service.send(
        UartTaskCancelRequest(
            message_type="task_cancel",
            robot_id=1,
            task_id=10,
        ),
        ack_timeout_seconds=0.5,
        max_retries=2,
    )

    assert result["task"]["state"] == "cancelled"
    assert isinstance(uart.sent[-1], TaskCancel)
    assert not service.has_active_tasks()


# ─────────────────────────────────────────────────────────────────────────────
def test_uart_message_discriminator_and_numeric_limits() -> None:
    """Kiểm tra discriminator và giới hạn số của payload UART."""
    adapter = TypeAdapter(UartMessageRequest)

    parsed = adapter.validate_python(
        {
            "message_type": "task_cancel",
            "robot_id": 2,
            "task_id": 255,
        }
    )
    assert isinstance(parsed, UartTaskCancelRequest)

    move = adapter.validate_python(
        {
            "message_type": "move_to_point",
            "robot_id": 2,
            "x": 1.0,
            "y": 2.0,
            "theta": 0.5,
        }
    )
    assert isinstance(move, UartMoveToPointRequest)

    try:
        adapter.validate_python(
            {
                "message_type": "task_assign",
                "robot_id": 256,
                "task_id": 1,
                "x": 0,
                "y": 0,
                "theta": 0,
            }
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("robot_id ngoài uint8 phải bị từ chối")


# ─────────────────────────────────────────────────────────────────────────────
def test_move_to_point_api_sends_without_tracking_task() -> None:
    """Kiểm tra API gửi MoveToPoint mà không tạo manual task."""
    uart = FakeManualUart()
    request = _move_request()
    state_store = _idle_robot_store()

    with (
        patch("api.services.uart.uart_manager_v2", uart),
        patch("api.services.uart.robot_move_registry", RobotMoveRegistry()),
        patch(
            "api.services.robot_heartbeat.robot_heartbeat_service",
            SimpleNamespace(state_store=state_store),
        ),
        patch(
            "api.services.runtime.get_runtime_status",
            return_value={"thread_alive": False, "state": "stopped"},
        ),
        patch(
            "api.services.uart.config_store.get_config_data",
            return_value={
                "robot_dispatch": {
                    "ack_timeout_seconds": 0.5,
                    "max_retries": 2,
                }
            },
        ),
        patch.object(uart_service.manual_robot_task_service, "send") as task_send,
    ):
        result = uart_service.send_move_to_point(request)

    assert result == {
        "message_type": "move_to_point",
        "robot_id": 1,
        "move_id": 0,
        "acknowledged": True,
        "ack": {
            "result_code": 0,
            "result": "ACCEPTED",
            "reason_code": 0,
            "reason": "NONE",
        },
        "target": {"x": 1.5, "y": 2.0, "theta": 0.25},
    }
    assert len(uart.sent) == 1
    assert isinstance(uart.sent[0], MoveToPoint)
    assert uart.sent[0].move_id == 0
    assert uart.retry_references == [0]
    task_send.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
def test_move_to_point_api_rejects_second_command_while_active() -> None:
    """Kiểm tra API không gửi MoveToPoint thứ hai khi lệnh trước chưa xong."""
    uart = FakeManualUart()
    state_store = _idle_robot_store()
    registry = RobotMoveRegistry()

    with (
        patch("api.services.uart.uart_manager_v2", uart),
        patch("api.services.uart.robot_move_registry", registry),
        patch(
            "api.services.robot_heartbeat.robot_heartbeat_service",
            SimpleNamespace(state_store=state_store),
        ),
        patch(
            "api.services.runtime.get_runtime_status",
            return_value={"thread_alive": False, "state": "stopped"},
        ),
        patch(
            "api.services.uart.config_store.get_config_data",
            return_value={"robot_dispatch": {}},
        ),
    ):
        first = uart_service.send_move_to_point(_move_request())
        try:
            uart_service.send_move_to_point(_move_request())
        except HTTPException as exc:
            assert exc.status_code == 409
            assert "đang thực hiện" in exc.detail
        else:
            raise AssertionError("API phải từ chối lệnh thứ hai khi robot bận")

    assert first["move_id"] == 0
    assert len(uart.sent) == 1


# ─────────────────────────────────────────────────────────────────────────────
def test_move_to_point_api_rejects_missing_ack() -> None:
    """Kiểm tra API phân biệt trường hợp không nhận được ACK."""
    uart = FakeManualUart()
    uart.retry_acks = [None]
    state_store = _idle_robot_store()

    with (
        patch("api.services.uart.uart_manager_v2", uart),
        patch("api.services.uart.robot_move_registry", RobotMoveRegistry()),
        patch(
            "api.services.robot_heartbeat.robot_heartbeat_service",
            SimpleNamespace(state_store=state_store),
        ),
        patch(
            "api.services.runtime.get_runtime_status",
            return_value={"thread_alive": False, "state": "stopped"},
        ),
        patch(
            "api.services.uart.config_store.get_config_data",
            return_value={"robot_dispatch": {}},
        ),
    ):
        try:
            uart_service.send_move_to_point(_move_request())
        except HTTPException as exc:
            assert exc.status_code == 503
            assert exc.detail == "Không nhận được ACK cho lệnh MoveToPoint."
        else:
            raise AssertionError("API phải báo lỗi khi MoveToPoint không được ACK")


# ─────────────────────────────────────────────────────────────────────────────
def test_move_to_point_api_exposes_rejected_ack_reason() -> None:
    """Kiểm tra API trả đúng nguyên nhân khi robot từ chối MoveToPoint."""
    uart = FakeManualUart()
    uart.retry_acks = [
        Ack(
            robot_id=1,
            acked_type=MessageType.MOVE_TO_POINT,
            reference_id=0,
            result_code=AckResultCode.REJECTED,
            reason_code=AckReasonCode.ROBOT_BUSY,
        )
    ]
    state_store = _idle_robot_store()

    with (
        patch("api.services.uart.uart_manager_v2", uart),
        patch("api.services.uart.robot_move_registry", RobotMoveRegistry()),
        patch(
            "api.services.robot_heartbeat.robot_heartbeat_service",
            SimpleNamespace(state_store=state_store),
        ),
        patch(
            "api.services.runtime.get_runtime_status",
            return_value={"thread_alive": False, "state": "stopped"},
        ),
        patch(
            "api.services.uart.config_store.get_config_data",
            return_value={"robot_dispatch": {}},
        ),
    ):
        try:
            uart_service.send_move_to_point(_move_request())
        except HTTPException as exc:
            assert exc.status_code == 409
            assert "ROBOT_BUSY" in exc.detail
            assert "reason_code=1" in exc.detail
        else:
            raise AssertionError("API phải trả nguyên nhân ACK bị từ chối")


# ─────────────────────────────────────────────────────────────────────────────
def test_manual_api_is_blocked_while_runtime_is_running() -> None:
    """Kiểm tra API UART thủ công bị chặn khi runtime đang chạy."""
    with patch(
        "api.services.runtime.get_runtime_status",
        return_value={"thread_alive": True, "state": "running"},
    ):
        try:
            uart_service.send_uart_message(_assign_request())
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("Manual API phải bị khóa khi Runtime đang chạy")


# ─────────────────────────────────────────────────────────────────────────────
def test_runtime_start_is_blocked_by_active_manual_task() -> None:
    """Kiểm tra runtime không khởi động khi còn manual task hoạt động."""
    manager = RuntimeManager()

    with patch(
        "api.services.manual_robot_task.manual_robot_task_service.has_active_tasks",
        return_value=True,
    ):
        try:
            manager.start()
        except ValueError as exc:
            assert "manual robot task" in str(exc)
        else:
            raise AssertionError("Runtime phải bị khóa khi manual task đang active")


# ─────────────────────────────────────────────────────────────────────────────
def test_runtime_start_is_blocked_by_active_manual_move() -> None:
    """Kiểm tra runtime không khởi động khi robot còn MoveToPoint hoạt động."""
    manager = RuntimeManager()

    with (
        patch(
            "api.services.manual_robot_task.manual_robot_task_service.has_active_tasks",
            return_value=False,
        ),
        patch(
            "api.services.robot_move.robot_move_registry.has_any_active_move",
            return_value=True,
        ),
    ):
        try:
            manager.start()
        except ValueError as exc:
            assert "manual robot move" in str(exc)
        else:
            raise AssertionError("Runtime phải bị khóa khi robot đang di chuyển")
