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
    detector.is_running = True
    detector.run()

# Quản lý vòng đời ứng dụng (Khởi động các Thread chạy ngầm ở đây)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Cấp quyền cho router truy cập vào biến AI và Queue
    app.state.detector = detector
    app.state.data_queue = data_queue
    app.state.ai_thread = None

    # 1. Bật luồng AI
    if config.get("auto_start", False):
        app.state.ai_thread = threading.Thread(target=start_ai_loop, daemon=True)
        app.state.ai_thread.start()
    else:
        detector.is_running = False
        LOGGER.info("Bỏ qua chạy AI do auto_start=false.")
    
    # 2. Bật luồng đọc UART cho Robot
    threading.Thread(target=uart_reader_worker, daemon=True).start()
    
    yield
    
    # Khắc phục lỗi kẹt Port 9621 khi Ctrl+C:
    # Khi self.show = True, thư viện aidcv tự động spawn một tiến trình con (WaitKey backend server).
    # Tiến trình con này kế thừa socket của Uvicorn. Nếu chỉ giết tiến trình mẹ, tiến trình con vẫn sống
    # và giữ chặt Port 9621. Do đó ta phải tìm và diệt tận gốc các tiến trình con này.
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
        "main:app", 
        host="0.0.0.0", 
        port=9621, 
        reload=False
    )