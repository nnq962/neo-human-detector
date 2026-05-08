
from utils import LOGGER, uart_manager
import time

data_points = [
    {"x": 1.5509509, "y": -0.6909566, "theta": -0.2611108},
    {"x": -0.7692372, "y": -1.9834429, "theta": -1.8264357},
    {"x": -1.8622463, "y": -0.2660847, "theta": 2.3308456}
]

while True:
    for point in data_points:
        x, y, theta = point["x"], point["y"], point["theta"]
        LOGGER.info(f"Đang gửi: x={x}, y={y}, theta={theta}")
        uart_manager.send_string(f"d:test,{x},{y},{theta}")
        
        # Chờ ESP32 nhận data, xử lý và phản hồi lại (100ms)
        time.sleep(0.1) 
        
        data = uart_manager.receive_data()
        if data:
            LOGGER.info(f"Kết quả nhận: {data}")
        
        time.sleep(10)

