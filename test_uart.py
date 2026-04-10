
import threading
import queue
import time
from utils import LOGGER, UartManager

# 1. Tạo một "Hàng đợi" an toàn để hai luồng giao tiếp với nhau
command_queue = queue.Queue(maxsize=10) # Lưu tối đa 10 lệnh chưa kịp gửi

# =================================================================
# LUỒNG PHỤ: Chuyên lo việc gửi/nhận UART (Chạy ngầm)
# =================================================================
def uart_worker_thread():
    LOGGER.debug("[THREAD] Bắt đầu khởi động luồng UART...")
    esp32 = UartManager(port='/dev/ttyS4', baudrate=115200)
    
    while True:
        # Kiểm tra xem có lệnh nào trong hộp thư không
        if not command_queue.empty():
            payload = command_queue.get() # Nhặt lệnh ra
            
            # Gửi cho ESP32
            esp32.send_json(payload)
            
            # Ở luồng này, bạn THA HỒ dùng sleep để chờ ESP32 phản hồi
            # Nó hoàn toàn KHÔNG làm chậm camera của bạn!
            time.sleep(0.05) 
            response = esp32.receive_data()
            if response:
                LOGGER.debug(f"[UART] ESP32 trả lời: {response}")
                
        else:
            # Nếu hộp thư trống, cũng có thể đọc xem ESP32 có chủ động gửi gì lên không
            response = esp32.receive_data()
            if response:
                 LOGGER.debug(f"[UART] ESP32 chủ động gửi: {response}")
                 
        # Ngủ một giấc siêu ngắn để không ăn hết 100% CPU của cái lõi chạy luồng này
        time.sleep(0.01)

# =================================================================
# LUỒNG CHÍNH: Xử lý ảnh (Chạy cực nhanh, không có delay)
# =================================================================
if __name__ == "__main__":
    # 2. Khởi động luồng UART chạy ngầm
    LOGGER.debug(f"Time: {time.time()}")
    uart_thread = threading.Thread(target=uart_worker_thread, daemon=True)
    uart_thread.start()
    
    LOGGER.debug("[MAIN] Bắt đầu xử lý ảnh...")
    LOGGER.debug(f"Time: {time.time()}")
    
    frame_count = 0
    try:
        while True:

            
            # ---> CODE XỬ LÝ ẢNH/AI CỦA BẠN Ở ĐÂY <---
            # Giả sử phát hiện được khuôn mặt ở tọa độ X=100, Y=200
            face_x, face_y = 100, 200 
            
            # 3. Thay vì gửi UART trực tiếp, ta NÉM VÀO QUEUE
            # Mẹo: Đừng ném liên tục mỗi frame. Ví dụ 5 frame mới ném 1 lần để ESP32 thở kịp
            frame_count += 1
            if frame_count % 5 == 0: 
                payload = {
                    "target": "SERVO_CAMERA",
                    "x": face_x,
                    "y": face_y
                }
                
                # Ném vào hộp thư (cực nhanh, tốn 0.0001 giây)
                if not command_queue.full():
                    command_queue.put(payload)
            

            
    except KeyboardInterrupt:
        LOGGER.debug("\n[MAIN] Đang tắt hệ thống...")
        
    finally:
        pass