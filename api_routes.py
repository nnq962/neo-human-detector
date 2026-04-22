import aidcv as cv2
import json
from fastapi import APIRouter, Response, HTTPException, Request, WebSocket, WebSocketDisconnect
from collections import deque
import asyncio
from utils import LOGGER, uart_manager
import time

router = APIRouter()

# Hàng đợi chứa gói tin mới nhất
robot_data_queue = deque(maxlen=1)

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
        time.sleep(0.01)

# (Thread UART được khởi động từ main.py lifespan)

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
@router.get("/api/get-snapshot")
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
@router.post("/api/save-config")
async def save_config(request: Request):
    try:
        # Nhận chuỗi JSON từ giao diện Web gửi xuống
        new_config = await request.json()
        
        # Ghi đè vào file config.json
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(new_config, f, indent=4, ensure_ascii=False)
            
        # Nạp cấu hình nóng (Hot Reload) vào AI đang chạy
        if hasattr(request.app.state, "detector"):
            request.app.state.detector.update_dynamic_config(
                new_conf=new_config.get("conf"),
                new_roi_check_mode=new_config.get("roi_check_mode"),
                new_monitored_areas=new_config.get("monitored_areas")
            )
            
        return {"status": "success", "message": "Đã lưu cấu hình ROI thành công!"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu file: {str(e)}")


# ==========================================
# API 3: LẤY DATA JSON HIỆN TẠI
# ==========================================
@router.get("/api/get-config")
def get_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

# ==========================================
# WebSocket 1: GỬI LỆNH ĐIỀU KHIỂN ROBOT
# ==========================================
@router.websocket("/ws/robot")
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
# WebSocket 2: GỬI BBOXES TỚI FRONTEND
# ==========================================
@router.websocket("/ws/bboxes")
async def websocket_bboxes(websocket: WebSocket):
    """Endpoint WebSocket để Frontend kết nối vào lấy dữ liệu."""
    await websocket.accept()
    LOGGER.info("Client đã kết nối WebSocket BBoxes thành công!")
    try:
        while True:
            # Lấy data_queue từ app state (được gán trong main.py)
            data_queue = websocket.app.state.data_queue
            
            # Lấy data từ queue và gửi đi
            if not data_queue.empty():
                payload = data_queue.get()
                await websocket.send_json(payload)
            else:
                # Nghỉ 10ms để nhường CPU, tránh treo event loop
                await asyncio.sleep(0.01) 
    except WebSocketDisconnect:
        LOGGER.info("Client đã ngắt kết nối WebSocket BBoxes.")
    except Exception as e:
        LOGGER.error(f"Lỗi kết nối WS BBoxes: {e}")