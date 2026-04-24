from utils import LOGGER, uart_manager
import time

i = 0
while True:
    uart_manager.send_string(f"d:test,{i},{i},{i}")
    
    # THÊM DÒNG NÀY: Chờ ESP32 nhận data, xử lý và phản hồi lại (100ms)
    time.sleep(0.1) 
    
    data = uart_manager.receive_data()
    LOGGER.info(f"Kết quả nhận: {data}")
    
    i += 1
    time.sleep(1)
