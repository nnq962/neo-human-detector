"""
Giả lập DISPATCHER: mở cổng UART ảo /tmp/ttyV0.
Chạy song song với uart_v2_robot_sim.py (đang mở /tmp/ttyV1).

- Nhận Heartbeat liên tục từ Robot, in ra vị trí/trạng thái.
- Mỗi TASK_ASSIGN_EVERY giây thì gửi 1 TaskAssign bằng send_with_retry()
  để kiểm chứng cơ chế tự gửi lại khi ACK bị rớt (xem uart_v2_robot_sim.py,
  nơi giả lập rớt ACK ngẫu nhiên).
"""

import time

from uart_v2.uart_manager import UartManagerV2
from src.robot_dispatch_v2.datatypes import Heartbeat, MessageType, TaskAssign

PORT = "/tmp/ttyV0"
TASK_ASSIGN_EVERY = 3  # cứ mỗi 3 giây gửi thêm 1 TaskAssign

manager = UartManagerV2(port=PORT, baudrate=115200, timeout=1)


def on_heartbeat(msg: Heartbeat):
    print(
        f"[NHẬN] Heartbeat robot={msg.robot_id} x={msg.x:.2f}m y={msg.y:.2f}m "
        f"theta={msg.theta}rad state={msg.state_code}"
    )


manager.set_handler(MessageType.HEARTBEAT, on_heartbeat)

if not manager.connect():
    print(f"Không mở được cổng {PORT}, kiểm tra lại socat đã chạy chưa.")
    raise SystemExit(1)

print(f"Đã mở {PORT}, đang lắng nghe Heartbeat và gửi TaskAssign định kỳ. Ctrl+C để dừng.")

seq = 0
try:
    while True:
        seq += 1
        task = TaskAssign(robot_id=1, task_id=seq, x=3.0 + seq * 0.1, y=4.0, theta=1.0)
        print(f"[GỬI] TaskAssign task_id={task.task_id}, chờ ACK...")
        acked = manager.send_with_retry(task, task_id=task.task_id, timeout=1.0, max_retries=3)
        print(f"[KẾT QUẢ] TaskAssign task_id={task.task_id} được ACK: {acked}")
        time.sleep(TASK_ASSIGN_EVERY)
except KeyboardInterrupt:
    print("\nDừng gửi.")
finally:
    manager.close()
