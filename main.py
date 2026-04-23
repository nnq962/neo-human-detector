import threading
import queue
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from human_detector import HumanDetector
from api_routes import router as api_router, uart_reader_worker 
from utils import load_config, LOGGER
from utils.ai_service import do_start_ai

CONFIG_FILE = "config.json"

# Quản lý vòng đời ứng dụng (Khởi động các Thread chạy ngầm ở đây)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi tạo Detector & Queue bên trong lifespan để tránh bị chạy 2 lần do double import
    config = load_config(CONFIG_FILE)
    data_queue = queue.Queue(maxsize=1)
    detector = HumanDetector(
        source=config.get("source", 0),
        conf=config.get("conf", 0.5),
        imgsz=config.get("imgsz", 640),
        device=config.get("device", "cpu"),
        show=config.get("show", False),
        roi_check_mode=config.get("roi_check_mode", "center"),
        monitored_areas=config.get("monitored_areas", None),
        display_scale=config.get("display_scale", 0.55),
        ws_queue=data_queue
    )

    # Cấp quyền cho router truy cập vào biến AI và Queue
    app.state.detector = detector
    app.state.data_queue = data_queue
    app.state.ai_thread = None

    # 1. Bật luồng AI (dùng chung logic với API start-ai)
    if config.get("auto_start", False):
        do_start_ai(app.state)
    else:
        detector.is_running = False
        LOGGER.info("Bỏ qua chạy AI do auto_start=false.")
    
    # 2. Bật luồng đọc UART cho Robot
    threading.Thread(target=uart_reader_worker, daemon=True).start()
    
    yield

    LOGGER.info("Server đang tắt... Tiến hành dọn dẹp các tiến trình con của AidCV.")
    try:
        import aidcv as cv2
        cv2.destroyAllWindows()
    except Exception:
        pass

    try:
        import psutil, os, signal
        parent = psutil.Process(os.getpid())
        for child in parent.children(recursive=True):
            os.kill(child.pid, signal.SIGKILL)
    except Exception as e:
        LOGGER.error(f"Lỗi khi dọn dẹp tiến trình con: {e}")
        
    import os
    os._exit(0)

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
        app,          # Truyền object trực tiếp thay vì string "main:app" để tránh double import
        host="0.0.0.0", 
        port=9621, 
        reload=False
    )