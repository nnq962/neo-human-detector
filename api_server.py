import aidcv as cv2  # Hoặc import cv2 nếu chạy trên PC
import json
from fastapi import FastAPI, Response, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import threading
from collections import deque
import asyncio
from utils import LOGGER, uart_manager

app = FastAPI(title="ROI Config API")

# Hàng đợi chứa gói tin mới nhất
robot_data_queue = deque(maxlen=1)

# Cấu hình CORS để Web UI (Frontend) có thể gọi API mà không bị chặn
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Trong thực tế nên để IP của Frontend, demo thì để "*"
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONFIG_FILE = "config.json"

# Luồng đọc UART     
def uart_reader_worker():
    """Hàm này chạy trong thread riêng để đọc dữ liệu từ ESP32"""
    LOGGER.info("Thread UART đang lắng nghe...")
    while True:
        data = uart_manager.receive_data()
        if data and isinstance(data, dict):
            robot_data_queue.append(data)
        # Nghỉ cực ngắn để CPU không quá tải
        import time
        time.sleep(0.01)

# Event khi server khởi động
@app.on_event("startup")
async def startup_event():
    # Chạy thread UART
    thread = threading.Thread(target=uart_reader_worker, daemon=True)
    thread.start()
    LOGGER.info("Hệ thống UART đã sẵn sàng!")

def get_rtsp_url():
    """Hàm đọc RTSP URL từ file config.json hiện tại"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config.get("source", "")
    except Exception:
        # Nếu chưa có file config, dùng URL mặc định của bạn
        return "rtsp://admin:phenikaaneo%40@10.70.22.159:554/Streaming/Channels/101"

# ==========================================
# API 1: CHỤP ẢNH SNAPSHOT TỪ CAMERA
# ==========================================
@app.get("/api/get-snapshot")
def get_snapshot():
    rtsp_url = get_rtsp_url()
    if not rtsp_url:
        raise HTTPException(status_code=400, detail="Không tìm thấy RTSP URL trong config.")

    LOGGER.info(f"Đang chụp ảnh từ: {rtsp_url}")
    
    # Mở luồng, chụp 1 frame và nhả luồng ngay lập tức
    cap = cv2.VideoCapture(rtsp_url)
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise HTTPException(status_code=500, detail="Không thể kết nối đến Camera.")

    # Mã hóa ma trận ảnh (Numpy Array) thành định dạng JPEG
    success, buffer = cv2.imencode('.jpg', frame)
    if not success:
        raise HTTPException(status_code=500, detail="Lỗi mã hóa ảnh JPEG.")

    # Trả về dữ liệu nhị phân (bytes) của bức ảnh với Header là image/jpeg
    return Response(content=buffer.tobytes(), media_type="image/jpeg")


# ==========================================
# API 2: LƯU CẤU HÌNH TỪ WEB XUỐNG FILE JSON
# ==========================================
@app.post("/api/save-config")
async def save_config(request: Request):
    try:
        # Nhận chuỗi JSON từ giao diện Web gửi xuống
        new_config = await request.json()
        
        # Ghi đè vào file config.json
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(new_config, f, indent=4, ensure_ascii=False)
            
        return {"status": "success", "message": "Đã lưu cấu hình ROI thành công!"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu file: {str(e)}")


# ==========================================
# API 3: LẤY DATA JSON HIỆN TẠI
# ==========================================
@app.get("/api/get-config")
def get_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

# ==========================================
# API 4: GỬI LỆNH ĐIỀU KHIỂN ROBOT (WS)
# ==========================================
@app.websocket("/ws/robot")
async def websocket_robot(websocket: WebSocket):
    await websocket.accept()
    LOGGER.info("Client đã kết nối WebSocket.")
    
    # Biến cờ để nhớ xem dữ liệu cuối cùng mình gửi cho Client này là gì
    last_sent_data = None 
    
    try:
        while True:
            # 1. Kiểm tra xem deque có dữ liệu không (deque dùng len() thay vì empty())
            if len(robot_data_queue) > 0:
                # Lấy phần tử mới nhất (bên phải cùng) mà KHÔNG xóa nó khỏi deque
                # Điều này giúp nhiều màn hình Web có thể cùng đọc 1 tọa độ
                current_data = robot_data_queue[-1]
                
                # 2. CHỈ GỬI ĐI nếu tọa độ này là mới (khác với cái vừa gửi lúc nãy)
                if current_data != last_sent_data:
                    await websocket.send_json(current_data)
                    last_sent_data = current_data  # Cập nhật lại cờ
            
            # 3. Nghỉ ngắn 10ms để không làm cháy CPU của mạch nhúng
            await asyncio.sleep(0.01) 
            
    except WebSocketDisconnect:
        LOGGER.info("Client đã ngắt kết nối.")
    except Exception as e:
        LOGGER.error(f"Lỗi WebSocket: {e}")

# ==========================================
# GIAO DIỆN
# ==========================================
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    # Chạy server ở port 8000, lắng nghe mọi IP trong mạng LAN
    host = "0.0.0.0"
    port = 9620
    LOGGER.info(f"Đang khởi động tại http://{host}:{port}")
    uvicorn.run(
        "api_server:app", 
        host=host, 
        port=port, 
        reload=False
    )