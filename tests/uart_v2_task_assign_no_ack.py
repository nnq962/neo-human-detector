"""Gửi một TaskAssign qua UART đúng một lần, không chờ ACK và không retry.

Chạy từ thư mục gốc của project, ví dụ:

    uv run python tests/uart_v2_task_assign_no_ack.py \
        --port /dev/ttyUSB0 --robot-id 1 --task-id 10 \
        --x 1.23 --y 4.56 --theta 1.57
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Cho phép chạy trực tiếp bằng ``python tests/<file>.py`` từ mọi working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.robot_dispatch_v2.datatypes import TaskAssign
from uart_v2.uart_manager import BINARY_START_BYTE, UartManagerV2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gửi một message TaskAssign qua UART mà không chờ ACK.",
    )
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Cổng UART")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--robot-id", type=int, default=1)
    parser.add_argument("--task-id", type=int, default=10)
    parser.add_argument("--x", type=float, default=1.23, help="Tọa độ đích x (m)")
    parser.add_argument("--y", type=float, default=4.56, help="Tọa độ đích y (m)")
    parser.add_argument("--theta", type=float, default=1.57, help="Góc đích (rad)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manager = UartManagerV2(
        port=args.port,
        baudrate=args.baudrate,
        timeout=1,
    )

    if not manager.connect():
        print(f"[LỖI] Không mở được UART {args.port}: {manager.last_error}")
        return 1

    task = TaskAssign(
        robot_id=args.robot_id,
        task_id=args.task_id,
        x=args.x,
        y=args.y,
        theta=args.theta,
    )

    try:
        # In ra đúng gói nhị phân sẽ ghi ra cổng UART (start byte + length + body).
        body = task.encode()  # message_type + payload + checksum
        packet = bytes([BINARY_START_BYTE, len(body)]) + body
        print(f"[NHỊ PHÂN] {len(packet)} byte: {packet.hex(' ')}")
        print(f"[NHỊ PHÂN] bin: {' '.join(f'{b:08b}' for b in packet)}")

        # Chỉ gửi đúng một lần. Không dùng send_with_retry() và không đợi ACK.
        sent = manager.send_message(task)
        if not sent:
            print(f"[LỖI] Không gửi được TaskAssign: {manager.last_error}")
            return 1

        print(
            "[ĐÃ GỬI - KHÔNG CHỜ ACK] "
            f"robot_id={task.robot_id}, task_id={task.task_id}, "
            f"x={task.x}m, y={task.y}m, theta={task.theta}rad"
        )
        return 0
    finally:
        manager.close()


if __name__ == "__main__":
    raise SystemExit(main())
