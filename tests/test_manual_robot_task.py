from unittest.mock import patch

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError

from api.models.uart import UartMessageRequest, UartTaskAssignRequest, UartTaskCancelRequest
from api.services.manual_robot_task import ManualRobotTaskService
from api.services.runtime import RuntimeManager
from api.services import uart as uart_service
from src.robot_dispatch_v2.datatypes import Ack, MessageType, TaskAssign, TaskCancel, TaskStatus, TaskStatusCode


# ─────────────────────────────────────────────────────────────────────────
class FakeManualUart:
    """UART V2 giả để test manual task mà không mở serial."""

    def __init__(self) -> None:
        self.connected = True
        self.handlers = {}
        self.sent = []
        self.retry_outcomes = []

    def add_handler(self, message_type, handler) -> None:
        self.handlers[int(message_type)] = handler

    def remove_handler(self, message_type, handler) -> None:
        if self.handlers.get(int(message_type)) == handler:
            self.handlers.pop(int(message_type))

    def send_message(self, message) -> bool:
        self.sent.append(message)
        return True

    def send_with_retry(
        self,
        message,
        task_id,
        timeout=1.0,
        max_retries=5,
    ) -> bool:
        self.sent.append(message)
        if self.retry_outcomes:
            return self.retry_outcomes.pop(0)
        return True

    def is_connected(self) -> bool:
        return self.connected

    def emit(self, message) -> None:
        handler = self.handlers.get(int(message.MESSAGE_TYPE))
        if handler is not None:
            handler(message)


# ──────────────────────────────────────────────────────────────────────────
def _assign_request(task_id: int = 10) -> UartTaskAssignRequest:
    return UartTaskAssignRequest(
        message_type="task_assign",
        robot_id=1,
        task_id=task_id,
        x=1.5,
        y=2.0,
        theta=0.25,
    )


# ───────────────────────────────────────────────────────────────────────────
def test_manual_assign_tracks_status_and_acknowledges_task_status() -> None:
    uart = FakeManualUart()
    service = ManualRobotTaskService(uart)
    service.register_uart_handlers()

    result = service.send(
        _assign_request(),
        ack_timeout_seconds=0.5,
        max_retries=2,
    )

    assert result["acknowledged"]
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


# ──────────────────────────────────────────────────────────────────────────
def test_manual_cancel_requires_and_finishes_active_task() -> None:
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


# ───────────────────────────────────────────────────────────────────────────
def test_uart_message_discriminator_and_numeric_limits() -> None:
    adapter = TypeAdapter(UartMessageRequest)

    parsed = adapter.validate_python(
        {
            "message_type": "task_cancel",
            "robot_id": 2,
            "task_id": 255,
        }
    )
    assert isinstance(parsed, UartTaskCancelRequest)

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


# ─────────────────────────────────────────────────────────────────────────
def test_manual_api_is_blocked_while_runtime_is_running() -> None:
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


# ─────────────────────────────────────────────────────────────────────────
def test_runtime_start_is_blocked_by_active_manual_task() -> None:
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
