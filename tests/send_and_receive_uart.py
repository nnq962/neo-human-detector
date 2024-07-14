import time
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    for send_string in range(1, 1001):
        uart_manager.send_string(str(send_string))
        time.sleep(0.5)
