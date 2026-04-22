import threading
import queue
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from human_detector import HumanDetector
from api_server import router as api_router, uart_reader_worker 
from utils import load_config, LOGGER

CONFIG_FILE = "config.json"

# Data queue gửi cho frontend
data_queue = queue.Queue(maxsize=1)

# Khởi tạo Detector
config = load_config(CONFIG_FILE)
detector = HumanDetector(
    source=config.get("source", 0),
    conf=config.get("conf", 0.5),
    imgsz=config.get("imgsz", 640),
    device=config.get("device", "cpu"),
    show=config.get("show", True),
    roi_check_mode=config.get("roi_check_mode", "center"),
    monitored_areas=config.get("monitored_areas", None),
    display_scale=config.get("display_scale", 0.55),
    ws_queue=data_queue
)

def start_ai_loop():
    LOGGER.info("Bắt đầu chạy luồng AI HumanDetector...")
    detector.run()

# Quản lý vòng đời ứng dụng (Khởi động các Thread chạy ngầm ở đây)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Cấp quyền cho router truy cập vào biến AI và Queue
    app.state.detector = detector
    app.state.data_queue = data_queue

    # 1. Bật luồng AI
    threading.Thread(target=start_ai_loop, daemon=True).start()
    
    # 2. Bật luồng đọc UART cho Robot
    threading.Thread(target=uart_reader_worker, daemon=True).start()
    
    yield

# Khởi tạo App chính
app = FastAPI(title="Edge AI Central Server", lifespan=lifespan)

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gắn toàn bộ API và WebSockets từ file api_routes vào
app.include_router(api_router)

# Mount thư mục giao diện Web
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":    
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=9621, 
        reload=False
    )