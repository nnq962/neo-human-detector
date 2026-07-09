"""
Giả lập ROBOT: mở cổng UART ảo /tmp/ttyV1.
Chạy song song với uart_v2_dispatcher_sim.py (đang mở /tmp/ttyV0).

- Liên tục gửi Heartbeat về Dispatcher (đúng chiều thật: Robot -> Dispatcher).
- Khi nhận TaskAssign từ Dispatcher thì giả lập rớt ACK ngẫu nhiên
  (ACK_DROP_RATE) để kiểm chứng bên Dispatcher có thật sự gửi lại
  (retry qua send_with_retry) hay không.
"""

import random
import time

from uart_v2.uart_manager import UartManagerV2
from src.robot_dispatch_v2.datatypes import Ack, Heartbeat, MessageType, RobotStateCode, TaskAssign

PORT = "/tmp/ttyV1"
ACK_DROP_RATE = 0.6  # xác suất "làm rơi" ACK, giả lập lỗi truyền/robot không kịp trả lời

manager = UartManagerV2(port=PORT, baudrate=115200, timeout=1)


def on_task_assign(msg: TaskAssign):
    print(
        f"[NHẬN] TaskAssign robot={msg.robot_id} task_id={msg.task_id} "
        f"x={msg.x:.2f}m y={msg.y:.2f}m theta={msg.theta}rad"
    )

    if random.random() < ACK_DROP_RATE:
        print(f"    -> giả lập RỚT ACK cho task_id={msg.task_id}, không trả lời.")
        return

    ack = Ack(robot_id=msg.robot_id, acked_type=MessageType.TASK_ASSIGN, task_id=msg.task_id)
    ok = manager.send_message(ack)
    print(f"    -> gửi ACK cho task_id={msg.task_id}, thành công: {ok}")


manager.set_handler(MessageType.TASK_ASSIGN, on_task_assign)

if not manager.connect():
    print(f"Không mở được cổng {PORT}, kiểm tra lại socat đã chạy chưa.")
    raise SystemExit(1)

print(f"Đã mở {PORT}, bắt đầu gửi Heartbeat mỗi giây. Ctrl+C để dừng.")

seq = 0
try:
    while True:
        seq += 1
        hb = Heartbeat(
            robot_id=1,
            timestamp=int(time.time()),
            x=1.0 + seq * 0.01,
            y=2.0 + seq * 0.01,
            theta=0.5,
            state_code=RobotStateCode.SERVING,
        )
        ok = manager.send_message(hb)
        print(f"[GỬI] Heartbeat #{seq} x={hb.x:.2f} y={hb.y:.2f} theta={hb.theta} -> thành công: {ok}")
        time.sleep(1)
except KeyboardInterrupt:
    print("\nDừng gửi.")
finally:
    manager.close()
