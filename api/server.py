from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from api.routes import config, detector, websocket

app = FastAPI()

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cho phép tất cả các domain. Có thể thay bằng list cụ thể, vd: ["http://localhost:3000"]
    allow_credentials=True, # Cho phép gửi cookie, thông tin xác thực
    allow_methods=["*"],  # Cho phép tất cả các method HTTP (GET, POST, PUT, DELETE, OPTIONS...)
    allow_headers=["*"],  # Cho phép tất cả các header
)

# ────────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup_event():
    from api.services.config import get_config_data
    from api.services.detector import start
    from utils import LOGGER
    
    try:
        cfg = get_config_data()
        if cfg.get("auto_start", False):
            LOGGER.info("auto_start is TRUE. Starting detector automatically...")
            start()
    except Exception as e:
        LOGGER.error(f"Failed to auto-start detector: {e}")

# ────────────────────────────────────────────────────────────────
app.include_router(config.router,   prefix="/api/config")
app.include_router(detector.router, prefix="/api/detector")
app.include_router(websocket.router)

# ────────────────────────────────────────────────────────────────
# Mount frontend build
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")
