import serial
import json
import time
from utils.logger import LOGGER
from utils.load_config import load_config

CONFIG_FILE = "config.json"
DEFAULT_PORT = '/dev/ttyS4'
DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT = 1

class UartManager:
    def __init__(self, port=DEFAULT_PORT, baudrate=DEFAULT_BAUDRATE, timeout=DEFAULT_TIMEOUT):
        """Khởi tạo kết nối UART"""
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn = None
        self.connect()

    def connect(self):
        """Mở cổng Serial"""
        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            LOGGER.info(f"Đã kết nối UART tại {self.port}")
        except serial.SerialException as e:
            LOGGER.error(f"Lỗi mở cổng {self.port}: {e}")

    def send_json(self, data_dict):
        """Đóng gói Dictionary thành JSON và gửi đi"""
        if not self.serial_conn or not self.serial_conn.is_open:
            LOGGER.error("Cổng UART chưa mở.")
            return False
            
        try:
            # Chuyển dict thành chuỗi JSON. 
            # Bắt buộc thêm '\n' ở cuối để ESP32 biết đã hết 1 gói tin
            json_str = json.dumps(data_dict) + '\n' 
            self.serial_conn.write(json_str.encode('utf-8'))
            LOGGER.info(f"Send: {json_str.strip()}")
            return True
        except Exception as e:
            LOGGER.error(f"Lỗi khi gửi: {e}")
            return False

    def send_string(self, text_str):
        """Gửi chuỗi thuần qua UART"""
        if not self.serial_conn or not self.serial_conn.is_open:
            LOGGER.error("Cổng UART chưa mở.")
            return False
            
        try:
            # Nếu chuỗi chưa có \n thì thêm vào
            if not text_str.endswith('\n'):
                text_str += '\n'
            self.serial_conn.write(text_str.encode('utf-8'))
            LOGGER.info(f"Send: {text_str.strip()}")
            return True
        except Exception as e:
            LOGGER.error(f"Lỗi khi gửi: {e}")
            return False

    def receive_data(self):
        """Đọc và tự động phân tích dữ liệu trả về từ ESP32"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return None
            
        try:
            if self.serial_conn.in_waiting > 0:
                raw_data = self.serial_conn.readline().decode('utf-8').strip()
                if not raw_data:
                    return None
                    
                # Thử parse JSON (nếu ESP32 gửi về dạng JSON)
                try:
                    parsed_data = json.loads(raw_data)
                    # LOGGER.info(f"Recv: {parsed_data}")
                    return parsed_data
                except json.JSONDecodeError:
                    # Nếu ESP32 chỉ in log dạng text bình thường
                    # LOGGER.info(f"Recv: {raw_data}")
                    return raw_data
        except Exception as e:
            LOGGER.error(f"Lỗi khi đọc: {e}")
            
        return None

    def close(self):
        """Đóng kết nối an toàn"""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            LOGGER.info("Đã ngắt kết nối UART.")

import os

# Đường dẫn tuyệt đối đến config.json để tránh lỗi khi import từ thư mục khác
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")

config = load_config(CONFIG_FILE)

uart_manager = UartManager(
    port=config.get("uart_port", DEFAULT_PORT), 
    baudrate=config.get("uart_baudrate", DEFAULT_BAUDRATE),
    timeout=DEFAULT_TIMEOUT
)
# =================================================================
# CÁCH SỬ DỤNG (Bạn có thể import class này vào file khác)
# =================================================================
if __name__ == "__main__":
    # 1. Khởi tạo đối tượng
    esp32 = UartManager(port='/dev/ttyS4', baudrate=115200)

    try:
        while True:
            # 2. Tạo một gói dữ liệu điều khiển (Dictionary)
            payload = {
                "device": "LED_MAIN",
                "action": "ON",
                "brightness": 85,
                "color": [255, 0, 0] # Đỏ
            }
            
            # Gửi đi
            esp32.send_json(payload)
            
            # Chờ 0.1s và kiểm tra phản hồi
            time.sleep(0.1)
            response = esp32.receive_data()
            
            LOGGER.debug("-" * 40)
            time.sleep(2) # Chờ 2s rồi lặp lại
            
    except KeyboardInterrupt:
        # Bắt sự kiện bấm Ctrl+C để đóng cổng an toàn
        esp32.close()
        LOGGER.infor("\nĐã thoát chương trình.")