"""Lắng nghe UART liên tục, in RAW bytes + giá trị đã giải mã (nếu hợp lệ).

Khác với `UartManagerV2.receive_message()` (chỉ trả về message đã giải mã hoặc
None, nuốt luôn raw bytes khi lỗi), script này in ra RAW hex của MỌI gói đọc
được - kể cả gói sai start byte, đọc thiếu byte, hay không giải mã được (CRC
sai/message_type lạ) - để có bằng chứng cụ thể đối chiếu với bên gửi khi nghi
ngờ wire format không khớp (xem `src/robot_dispatch_v2/message_spec.md`).

Chạy từ thư mục gốc của project, ví dụ:

    uv run python tests/uart_v2_listen_raw.py --port /dev/ttyUSB0
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Cho phép chạy trực tiếp bằng ``python tests/<file>.py`` từ mọi working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.robot_dispatch_v2.datatypes import MessageBase
from uart_v2.uart_manager import BINARY_START_BYTE, UartManagerV2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lắng nghe UART liên tục, in RAW bytes + giá trị giải mã được.",
    )
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Cổng UART")
    parser.add_argument("--baudrate", type=int, default=115200)
    return parser.parse_args()


def now() -> str:
    return time.strftime("%H:%M:%S")


def main() -> int:
    args = parse_args()
    manager = UartManagerV2(port=args.port, baudrate=args.baudrate, timeout=1)

    if not manager.connect():
        print(f"[LỖI] Không mở được UART {args.port}: {manager.last_error}")
        return 1

    # connect() tự khởi động 1 thread nền lắng nghe (start_listening()) - thread đó
    # cũng đọc trực tiếp từ serial_conn, sẽ tranh byte với vòng lặp thủ công bên dưới
    # nếu không tắt đi. Chỉ để đúng 1 nơi đọc cổng UART trong tiến trình này.
    manager.stop_listening()

    print(f"[SẴN SÀNG] Đang lắng nghe {args.port} @ {args.baudrate} baud. Ctrl+C để dừng.\n")

    try:
        while True:
            conn = manager.serial_conn
            if conn is None or not conn.is_open or conn.in_waiting <= 0:
                time.sleep(0.01)
                continue

            start = conn.read(1)
            if start[0] != BINARY_START_BYTE:
                print(f"[{now()}] [BYTE LẠ] không khớp start byte 0xAA: {start.hex(' ').upper()}")
                continue

            length_byte = conn.read(1)
            if not length_byte:
                print(f"[{now()}] [LỖI] mất kết nối giữa chừng khi đọc length byte")
                continue
            length = length_byte[0]

            body = conn.read(length)
            raw = start + length_byte + body
            if len(body) != length:
                print(
                    f"[{now()}] [ĐỌC THIẾU BYTE] khai báo length={length} "
                    f"nhưng chỉ đọc được {len(body)} byte: {raw.hex(' ').upper()}"
                )
                continue

            message = MessageBase.decode_any(body)
            if message is None:
                print(
                    f"[{now()}] [KHÔNG GIẢI MÃ ĐƯỢC] (CRC sai hoặc message_type không rõ) "
                    f"{len(raw)} byte: {raw.hex(' ').upper()}"
                )
            else:
                print(f"[{now()}] [OK] {len(raw)} byte: {raw.hex(' ').upper()}")
                print(f"           -> {message}")
    except KeyboardInterrupt:
        print("\n[DỪNG] Ctrl+C nhận được.")
    finally:
        manager.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
