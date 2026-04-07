import aidcv as cv2  # Hoặc import cv2 nếu chạy trên PC
import json
from fastapi import FastAPI, Response, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from utils import LOGGER

app = FastAPI(title="ROI Config API")

# Cấu hình CORS để Web UI (Frontend) có thể gọi API mà không bị chặn
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Trong thực tế nên để IP của Frontend, demo thì để "*"
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONFIG_FILE = "config.json"

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
# GIAO DIỆN
# ==========================================
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    # Chạy server ở port 8000, lắng nghe mọi IP trong mạng LAN
    LOGGER.info("Đang khởi động tại http://0.0.0.0:8000")
    uvicorn.run(
        "api_server:app", 
        host="0.0.0.0", 
        port=9620, 
        reload=True
    )