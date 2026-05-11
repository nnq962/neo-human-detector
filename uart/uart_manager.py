import os
import serial
import json
import time
import threading
from utils import LOGGER
from utils import load_config

CONFIG_FILE = "configs/default.yaml"
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
        
        # Dữ liệu mới nhất nhận được
        self.latest_received_data = None
        self.is_listening = False
        self.listen_thread = None
        
        self.connect()

    def connect(self):
        """Mở cổng Serial"""
        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            LOGGER.info(f"Đã kết nối UART tại {self.port}")
            self.start_listening()
        except serial.SerialException as e:
            LOGGER.error(f"Lỗi mở cổng {self.port}: {e}")

    def start_listening(self):
        """Khởi động luồng chạy ngầm để liên tục đọc dữ liệu"""
        if self.is_listening:
            return
            
        self.is_listening = True
        self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listen_thread.start()
        LOGGER.info("Đã khởi động luồng lắng nghe UART.")

    def stop_listening(self):
        """Dừng luồng lắng nghe"""
        self.is_listening = False
        if self.listen_thread and self.listen_thread.is_alive():
            self.listen_thread.join(timeout=2)
            
    def _listen_loop(self):
        """Vòng lặp ngầm liên tục gọi receive_data()"""
        while self.is_listening:
            
            # Kiểm tra nếu kết nối bị mất đột ngột
            if not self.serial_conn or not self.serial_conn.is_open:
                LOGGER.warning("Mất kết nối UART, đang thử kết nối lại...")
                time.sleep(2)
                self.connect()
                continue
            
            data = self.receive_data()
            if data is not None:
                if isinstance(data, dict):
                    # Nếu là JSON -> Cập nhật lên Web Config
                    self.latest_received_data = {
                        "timestamp": time.time(),
                        "payload": data
                    }
                elif isinstance(data, str):
                    # Nếu là Chuỗi -> Xử lý lệnh điều khiển
                    cmd = data.strip()
                    
                    if cmd == "sync":
                        # Gọi gửi lại payload UART gần nhất
                        from api.services.detector import sync_uart_payload
                        sync_uart_payload()
                        
                        # (Tuỳ chọn) Nếu bạn vẫn cần gửi cả cục JSON cho mục đích khác:
                        # from api.services.detector import get_latest_ws_payload
                        # payload = get_latest_ws_payload()
                        # if payload:
                        #     self.send_json({"type": "SYNC", "data": payload})
                            
            time.sleep(0.01) # Tránh ăn CPU

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
                raw_data = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                if not raw_data:
                    return None
                    
                # Thử parse JSON (nếu ESP32 gửi về dạng JSON)
                try:
                    parsed_data = json.loads(raw_data)
                    LOGGER.info(f"Recv: {parsed_data}")
                    return parsed_data
                except json.JSONDecodeError:
                    # Nếu ESP32 chỉ in log dạng text bình thường
                    LOGGER.info(f"Recv: {raw_data}")
                    return raw_data
        except Exception as e:
            LOGGER.error(f"Lỗi khi đọc: {e}")
            
        return None

    def close(self):
        """Đóng kết nối an toàn"""
        self.stop_listening()
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            LOGGER.info("Đã ngắt kết nối UART.")


# Đường dẫn tuyệt đối đến cấu hình mặc định (YAML)
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs/default.yaml")

config = load_config(CONFIG_FILE)
uart_cfg = config.get("uart", {})

uart_manager = UartManager(
    port=uart_cfg.get("port", DEFAULT_PORT), 
    baudrate=uart_cfg.get("baudrate", DEFAULT_BAUDRATE),
    timeout=DEFAULT_TIMEOUT
)