import aidcv as cv2
import json
from fastapi import APIRouter, Response, HTTPException, Request, WebSocket, WebSocketDisconnect
from collections import deque
import asyncio
from utils import LOGGER, uart_manager
from utils.ai_service import ai_lock, do_start_ai, do_stop_ai
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
        
        # 1. Đọc cấu hình cũ để so sánh
        old_config = {}
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                old_config = json.load(f)
        except Exception:
            pass
            
        # 2. Ghi đè vào file config.json
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(new_config, f, indent=4, ensure_ascii=False)
            
        # 3. Phân loại cấu hình thay đổi
        needs_restart = (
            old_config.get("source") != new_config.get("source") or
            old_config.get("imgsz") != new_config.get("imgsz") or
            old_config.get("show") != new_config.get("show")
        )
            
        # 4. Hành động
        if needs_restart:
            if not ai_lock.acquire(blocking=False):
                raise HTTPException(status_code=409, detail="Đang xử lý lệnh start/stop khác, vui lòng thử lại.")
            try:
                detector = getattr(request.app.state, "detector", None)
                # Nếu AI đang chạy thì mới Stop và Start lại
                if detector and getattr(detector, "is_running", False):
                    LOGGER.info("Phát hiện thay đổi source/imgsz/show, tiến hành khởi động lại AI...")
                    success, msg = do_stop_ai(request.app.state)
                    if not success:
                        return {"status": "warning", "message": f"Lưu thành công, nhưng khởi động lại thất bại: {msg}"}
                    do_start_ai(request.app.state)
            finally:
                ai_lock.release()
            return {"status": "success", "message": "Đã lưu cấu hình và khởi động lại AI thành công!"}
        else:
            # Nạp cấu hình nóng (Hot Reload) vào AI đang chạy
            if hasattr(request.app.state, "detector") and request.app.state.detector:
                request.app.state.detector.update_dynamic_config(
                    new_conf=new_config.get("conf"),
                    new_roi_check_mode=new_config.get("roi_check_mode"),
                    new_monitored_areas=new_config.get("monitored_areas")
                )
            return {"status": "success", "message": "Đã lưu cấu hình (Hot Reload) thành công!"}
    
    except HTTPException:
        raise
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
# API 4: LẤY TRẠNG THÁI AI RUNNING
# ==========================================
@router.get("/api/ai-status")
def get_ai_status(request: Request):
    detector = request.app.state.detector
    is_running = getattr(detector, "is_running", False)
    ai_thread = getattr(request.app.state, "ai_thread", None)
    thread_alive = ai_thread.is_alive() if ai_thread else False
    return {"is_running": is_running, "thread_alive": thread_alive}


# ==========================================
# API 5: START AI TASK
# ==========================================
@router.post("/api/start-ai")
def start_ai(request: Request):
    if not ai_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Đang xử lý lệnh start/stop khác, vui lòng thử lại.")
    try:
        detector = request.app.state.detector
        
        # Chống spam: AI đang chạy rồi
        if getattr(detector, "is_running", False):
            return {"status": "info", "message": "AI is already running"}
        
        # Chống spam: thread cũ chưa kết thúc hẳn
        ai_thread = getattr(request.app.state, "ai_thread", None)
        if ai_thread and ai_thread.is_alive():
            return {"status": "info", "message": "AI thread is still shutting down, please wait"}
        
        do_start_ai(request.app.state)
        return {"status": "success", "message": "AI started"}
    finally:
        ai_lock.release()


# ==========================================
# API 6: STOP AI TASK
# ==========================================
@router.post("/api/stop-ai")
def stop_ai(request: Request):
    if not ai_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Đang xử lý lệnh start/stop khác, vui lòng thử lại.")
    try:
        detector = request.app.state.detector
        
        # Chống spam: AI đã dừng rồi
        if not getattr(detector, "is_running", False):
            return {"status": "info", "message": "AI is already stopped"}
        
        success, message = do_stop_ai(request.app.state)
        status = "success" if success else "warning"
        return {"status": status, "message": message}
    finally:
        ai_lock.release()


# ==========================================
# API 7: RESTART AI TASK
# ==========================================
@router.post("/api/restart-ai")
def restart_ai(request: Request):
    if not ai_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Đang xử lý lệnh start/stop khác, vui lòng thử lại.")
    try:
        detector = request.app.state.detector
        
        # Bước 1: Dừng AI nếu đang chạy
        if getattr(detector, "is_running", False):
            success, msg = do_stop_ai(request.app.state)
            if not success:
                return {"status": "warning", "message": f"Restart failed at stop phase: {msg}"}
            LOGGER.info("Restart: Đã dừng AI thành công.")
        
        # Bước 2: Khởi động lại
        do_start_ai(request.app.state)
        LOGGER.info("Restart: Đã khởi động lại AI.")
        return {"status": "success", "message": "AI restarted successfully"}
    finally:
        ai_lock.release()


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