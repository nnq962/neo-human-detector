"""Gửi thử Heartbeat và TaskAssign qua UART V2 bằng thao tác chủ động."""

import time

from src.robot_dispatch_v2.datatypes import Ack, Heartbeat, MessageType, TaskAssign
from uart_v2.uart_manager import uart_manager_v2


# ─────────────────────────────────────────────────────────────────────────────
def on_heartbeat(message: Heartbeat) -> None:
    """In Heartbeat nhận được từ robot ra terminal."""
    print(
        f"[NHẬN] Robot {message.robot_id}: x={message.x}m, y={message.y}m, "
        f"theta={message.theta}rad, state={message.state_code}"
    )


# ─────────────────────────────────────────────────────────────────────────────
def on_ack(message: Ack) -> None:
    """In ACK nhận được từ robot ra terminal."""
    print(
        f"[NHẬN] ACK robot={message.robot_id}, "
        f"acked_type={message.acked_type}, "
        f"reference_id={message.reference_id}, result={message.result_code}, "
        f"reason={message.reason_code}"
    )


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    """Mở UART, gửi dữ liệu mẫu và chờ phản hồi cho tới khi người dùng dừng."""
    uart_manager_v2.set_handler(MessageType.HEARTBEAT, on_heartbeat)
    uart_manager_v2.set_handler(MessageType.ACK, on_ack)

    if not uart_manager_v2.connect():
        print("Không kết nối được UART, kiểm tra lại cổng/dây.")
        return 1

    try:
        heartbeat = Heartbeat(
            robot_id=1,
            timestamp=int(time.time()),
            x=12.856,
            y=3.247,
            theta=1.571,
            state_code=1,
        )
        print(f"Gửi Heartbeat thành công: {uart_manager_v2.send_message(heartbeat)}")

        task = TaskAssign(
            robot_id=1,
            task_id=10,
            x=1.23,
            y=4.56,
            theta=1.57,
        )
        acknowledged = uart_manager_v2.send_with_retry(
            task,
            reference_id=task.task_id,
            timeout=1.0,
            max_retries=3,
        )
        print(f"TaskAssign task_id={task.task_id} được ACK: {acknowledged}")

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
    finally:
        uart_manager_v2.close()


if __name__ == "__main__":
    raise SystemExit(main())
