"""Quản lý task robot gửi thủ công từ API, độc lập với vision."""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from typing import Optional, Protocol

from fastapi import HTTPException, status

from api.models.uart import UartMessageRequest, UartTaskAssignRequest
from src.robot_dispatch_v2.datatypes import (
    Ack,
    AckReasonCode,
    AckResultCode,
    MessageBase,
    MessageType,
    TaskAssign,
    TaskCancel,
    TaskStatus,
    TaskStatusCode,
)
from uart_v2.uart_manager import uart_manager_v2
from utils import LOGGER


ACTIVE_MANUAL_TASK_STATES = {
    "sending",
    "assigned",
    "in_progress",
    "cancel_pending",
}
robot_uart_operation_lock = threading.RLock()


# ──────────────────────────────────────────────────────────────────────────
class ManualTaskTransport(Protocol):
    """Phần API UART V2 mà service task thủ công cần sử dụng."""

    def add_handler(self, message_type: int, handler) -> None: ...

    def remove_handler(self, message_type: int, handler) -> None: ...

    def send_message(self, message: MessageBase) -> bool: ...

    def send_with_retry_ack(
        self,
        message: MessageBase,
        reference_id: int,
        timeout: float = 1.0,
        max_retries: int = 5,
    ) -> Optional[Ack]: ...

    def is_connected(self) -> bool: ...


# ──────────────────────────────────────────────────────────────────────────
@dataclass
class ManualRobotTask:
    """Snapshot của một task được gửi trực tiếp từ API."""

    robot_id: int
    task_id: int
    state: str
    created_at: float
    updated_at: float
    x: Optional[float] = None
    y: Optional[float] = None
    theta: Optional[float] = None


# ───────────────────────────────────────────────────────────────────────────
class ManualRobotTaskService:
    """Gửi task test, theo dõi state và ACK TaskStatus của robot."""

    def __init__(self, uart: ManualTaskTransport) -> None:
        self._uart = uart
        self._tasks: dict[tuple[int, int], ManualRobotTask] = {}
        self._handlers_registered = False
        self._lock = threading.RLock()

    # ─────────────────────────────────────────────────────────────────────
    def register_uart_handlers(self) -> None:
        """Nhận TaskStatus cho task thủ công trong suốt vòng đời FastAPI."""
        with self._lock:
            if self._handlers_registered:
                return
            self._uart.add_handler(MessageType.TASK_STATUS, self.on_task_status)
            self._handlers_registered = True

    # ───────────────────────────────────────────────────────────────────
    def close(self) -> None:
        """Gỡ handler khi FastAPI shutdown, không đóng UART dùng chung."""
        with self._lock:
            if not self._handlers_registered:
                return
            self._handlers_registered = False
        self._uart.remove_handler(MessageType.TASK_STATUS, self.on_task_status)

    # ───────────────────────────────────────────────────────────────────
    def send(
        self,
        request: UartMessageRequest,
        *,
        ack_timeout_seconds: float,
        max_retries: int,
    ) -> dict:
        """Gửi TaskAssign hoặc TaskCancel và chỉ thành công khi có ACK."""
        if not self._uart.is_connected():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="UART V2 is not connected.",
            )

        if isinstance(request, UartTaskAssignRequest):
            return self._send_assign(
                request,
                ack_timeout_seconds=ack_timeout_seconds,
                max_retries=max_retries,
            )

        return self._send_cancel(
            request.robot_id,
            request.task_id,
            ack_timeout_seconds=ack_timeout_seconds,
            max_retries=max_retries,
        )

    # ──────────────────────────────────────────────────────────────────
    def on_task_status(self, message: TaskStatus) -> None:
        """Cập nhật task thủ công và ACK status mà service sở hữu."""
        key = (message.robot_id, message.task_id)
        with self._lock:
            task = self._tasks.get(key)
            if task is None:
                return

        # Khi Runtime hoạt động, RobotDispatcherV2 là bên duy nhất ACK
        # TaskStatus. Nhánh này tránh ACK kép cho status trễ của task manual.
        from api.services.runtime import get_runtime_status

        if get_runtime_status()["thread_alive"]:
            return

        with self._lock:
            task = self._tasks.get(key)
            if task is None:
                return
            try:
                task_status = TaskStatusCode(message.status_code)
            except ValueError:
                LOGGER.warning(
                    "TaskStatus thủ công không hợp lệ: robot_id=%s, task_id=%s, status=%s",
                    message.robot_id,
                    message.task_id,
                    message.status_code,
                )
            else:
                task.state = task_status.name.lower()
                task.updated_at = time.time()

        acknowledged = self._uart.send_message(
            Ack(
                robot_id=message.robot_id,
                acked_type=MessageType.TASK_STATUS,
                reference_id=message.task_id,
                result_code=AckResultCode.ACCEPTED,
                reason_code=AckReasonCode.NONE,
            )
        )
        if not acknowledged:
            LOGGER.warning(
                "Không gửi được ACK cho TaskStatus thủ công: robot_id=%s, task_id=%s",
                message.robot_id,
                message.task_id,
            )

    # ───────────────────────────────────────────────────────────────────
    def has_active_tasks(self) -> bool:
        """Cho biết còn task thủ công có thể xung đột với Runtime hay không."""
        with self._lock:
            return any(
                task.state in ACTIVE_MANUAL_TASK_STATES
                for task in self._tasks.values()
            )

    # ──────────────────────────────────────────────────────────────────
    def snapshot(self) -> list[dict]:
        """Trả danh sách task mới cập nhật trước để hiển thị qua API."""
        with self._lock:
            tasks = sorted(
                self._tasks.values(),
                key=lambda task: task.updated_at,
                reverse=True,
            )
            return [asdict(task) for task in tasks]

    # ───────────────────────────────────────────────────────────────────
    def _send_assign(
        self,
        request: UartTaskAssignRequest,
        *,
        ack_timeout_seconds: float,
        max_retries: int,
    ) -> dict:
        key = (request.robot_id, request.task_id)
        now = time.time()
        with self._lock:
            if any(
                task.robot_id == request.robot_id
                and task.state in ACTIVE_MANUAL_TASK_STATES
                for task in self._tasks.values()
            ):
                raise ValueError(f"Robot {request.robot_id} already has a manual task.")

            self._tasks[key] = ManualRobotTask(
                robot_id=request.robot_id,
                task_id=request.task_id,
                state="sending",
                created_at=now,
                updated_at=now,
                x=request.x,
                y=request.y,
                theta=request.theta,
            )

        message = TaskAssign(
            robot_id=request.robot_id,
            task_id=request.task_id,
            x=request.x,
            y=request.y,
            theta=request.theta,
        )
        ack = self._uart.send_with_retry_ack(
            message,
            reference_id=request.task_id,
            timeout=ack_timeout_seconds,
            max_retries=max_retries,
        )
        if ack is None or ack.result_code != AckResultCode.ACCEPTED:
            with self._lock:
                self._tasks.pop(key, None)
            if ack is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Robot từ chối TaskAssign: "
                        f"{_ack_reason_name(ack.reason_code)} "
                        f"(reason_code={ack.reason_code})."
                    ),
                )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Robot did not acknowledge TaskAssign.",
            )

        with self._lock:
            task = self._tasks[key]
            if task.state == "sending":
                task.state = "assigned"
                task.updated_at = time.time()

        return self._build_send_result(
            "task_assign",
            request.robot_id,
            request.task_id,
            ack,
        )

    # ───────────────────────────────────────────────────────────────────
    def _send_cancel(
        self,
        robot_id: int,
        task_id: int,
        *,
        ack_timeout_seconds: float,
        max_retries: int,
    ) -> dict:
        key = (robot_id, task_id)
        with self._lock:
            task = self._tasks.get(key)
            if task is None or task.state not in ACTIVE_MANUAL_TASK_STATES:
                raise ValueError(
                    f"Manual task robot_id={robot_id}, task_id={task_id} is not active."
                )
            previous_state = task.state
            task.state = "cancel_pending"
            task.updated_at = time.time()

        ack = self._uart.send_with_retry_ack(
            TaskCancel(robot_id=robot_id, task_id=task_id),
            reference_id=task_id,
            timeout=ack_timeout_seconds,
            max_retries=max_retries,
        )
        if ack is None or ack.result_code != AckResultCode.ACCEPTED:
            with self._lock:
                task = self._tasks.get(key)
                if task is not None and task.state == "cancel_pending":
                    task.state = previous_state
                    task.updated_at = time.time()
            if ack is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Robot từ chối TaskCancel: "
                        f"{_ack_reason_name(ack.reason_code)} "
                        f"(reason_code={ack.reason_code})."
                    ),
                )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Robot did not acknowledge TaskCancel.",
            )

        with self._lock:
            task = self._tasks[key]
            if task.state not in {"completed", "failed"}:
                task.state = "cancelled"
                task.updated_at = time.time()

        return self._build_send_result("task_cancel", robot_id, task_id, ack)

    # ───────────────────────────────────────────────────────────────────
    def _build_send_result(
        self,
        message_type: str,
        robot_id: int,
        task_id: int,
        ack: Ack,
    ) -> dict:
        """Tạo response task thủ công kèm đầy đủ kết quả ACK."""
        with self._lock:
            task = self._tasks[(robot_id, task_id)]
            return {
                "message_type": message_type,
                "robot_id": robot_id,
                "task_id": task_id,
                "acknowledged": True,
                "ack": {
                    "result_code": int(ack.result_code),
                    "result": AckResultCode(ack.result_code).name,
                    "reason_code": int(ack.reason_code),
                    "reason": _ack_reason_name(ack.reason_code),
                },
                "task": asdict(task),
            }


# ─────────────────────────────────────────────────────────────────────────────
def _ack_reason_name(reason_code: int) -> str:
    """Đổi mã nguyên nhân ACK sang tên enum, có fallback cho mã lạ."""
    try:
        return AckReasonCode(reason_code).name
    except ValueError:
        return "UNKNOWN"


manual_robot_task_service = ManualRobotTaskService(uart_manager_v2)
