import time
import threading
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import LOGGER
from uart.uart_manager import uart_manager

data_points = [
    {"name":"zone1", "x": 1.5509509, "y": -0.6909566, "theta": -0.2611108},
    {"name":"zone2", "x": -0.7692372, "y": -1.9834429, "theta": -1.8264357},
    {"name":"zone3", "x": -1.8622463, "y": -0.2660847, "theta": 2.3308456}
]

# --- 1. LUỒNG NHẬN (RX THREAD) ---
# def receive_loop():
#     while True:
#         # Nhận liên tục, bất kể luồng chính đang làm gì
#         data = uart_manager.receive_data()
#         if data:
#             # LOGGER.info(f"Kết quả nhận: {data}")
#             pass
        
#         # Nghỉ 10ms để tránh làm CPU chạy 100%
#         time.sleep(0.01) 

# # Khởi chạy luồng nhận ở chế độ chạy ngầm (daemon)
# rx_thread = threading.Thread(target=receive_loop, daemon=True)
# rx_thread.start()

# --- 2. LUỒNG GỬI (TX THREAD - LUỒNG CHÍNH) ---
while True:
    for point in data_points:
        name, x, y, theta = point["name"], point["x"], point["y"], point["theta"]
        # LOGGER.info(f"Đang gửi: {name}, x={x}, y={y}, theta={theta}")
        uart_manager.send_string(f"d:{name},{x},{y},{theta}")
        
        # Bạn không cần chờ 0.1s ở đây nữa, luồng nhận sẽ tự bắt được phản hồi
        # Cứ gửi xong là chờ 10s như cũ
        time.sleep(10)