import time
from src.robot_dispatch_v2.datatypes import Ack, Heartbeat, MessageType, TaskAssign
from uart_v2.uart_manager import uart_manager_v2


# ---- BƯỚC 1: Đăng ký handler để xử lý khi nhận được Heartbeat ----
def on_heartbeat(msg: Heartbeat):
    print(f"[NHẬN] Robot {msg.robot_id}: x={msg.x}m, y={msg.y}m, theta={msg.theta}rad, state={msg.state_code}")

uart_manager_v2.set_handler(MessageType.HEARTBEAT, on_heartbeat)


# ---- BƯỚC 1b: Đăng ký handler để xem ACK trả về ----
def on_ack(msg: Ack):
    print(
        f"[NHẬN] ACK robot={msg.robot_id}, acked_type={msg.acked_type}, "
        f"reference_id={msg.reference_id}, result={msg.result_code}, "
        f"reason={msg.reason_code}"
    )

uart_manager_v2.set_handler(MessageType.ACK, on_ack)


# ---- BƯỚC 2: Mở kết nối UART (tự động khởi động thread lắng nghe nền) ----
if not uart_manager_v2.connect():
    print("Không kết nối được UART, kiểm tra lại cổng/dây.")
    exit(1)


# ---- BƯỚC 3: Tạo và gửi 1 gói Heartbeat ----
hb = Heartbeat(
    robot_id=1,
    timestamp=int(time.time()),
    x=12.856,
    y=3.247,
    theta=1.571,
    state_code=1,
)

success = uart_manager_v2.send_message(hb)
print(f"Gửi thành công: {success}")


# ---- BƯỚC 3b: Gửi 1 gói TaskAssign, tự động gửi lại nếu robot không ACK ----
task = TaskAssign(robot_id=1, task_id=10, x=1.23, y=4.56, theta=1.57)

acked = uart_manager_v2.send_with_retry(
    task,
    reference_id=task.task_id,
    timeout=1.0,
    max_retries=3,
)
print(f"TaskAssign task_id={task.task_id} được ACK: {acked}")


# ---- BƯỚC 4: Giữ chương trình chạy để thread nền có thời gian nhận và gọi on_heartbeat ----
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    uart_manager_v2.close()
