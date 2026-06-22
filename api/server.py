from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from api.routes import camera, detector, mediamtx, uart, websocket, zone_state_machine


def run_startup_tasks() -> None:
    from api.services.config_store import get_config_data
    from api.services.detector import start
    from api.services.load_cameras import sync_camera_paths, wait_for_mediamtx
    from utils import LOGGER

    try:
        cfg = get_config_data()
    except Exception as e:
        LOGGER.error(f"Failed to load config on startup: {e}")
        return

    try:
        wait_for_mediamtx()
        result = sync_camera_paths(cfg)
        LOGGER.info(
            "MediaMTX camera sync completed: "
            f"{result['synced']} synced, {result['failed']} failed, {result['skipped']} skipped."
        )
    except Exception as e:
        LOGGER.error(f"Failed to sync MediaMTX camera paths: {e}")

    try:
        if cfg.get("auto_start", False):
            LOGGER.info("auto_start is TRUE. Starting detector automatically...")
            start()
    except Exception as e:
        LOGGER.error(f"Failed to auto-start detector: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_startup_tasks()
    yield


app = FastAPI(lifespan=lifespan)

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cho phép tất cả các domain. Có thể thay bằng list cụ thể, vd: ["http://localhost:3000"]
    allow_credentials=True, # Cho phép gửi cookie, thông tin xác thực
    allow_methods=["*"],  # Cho phép tất cả các method HTTP (GET, POST, PUT, DELETE, OPTIONS...)
    allow_headers=["*"],  # Cho phép tất cả các header
)

# ────────────────────────────────────────────────────────────────
app.include_router(detector.router, prefix="/api/detector")
app.include_router(mediamtx.router, prefix="/api/mediamtx")
app.include_router(camera.router, prefix="/api/cameras")
app.include_router(zone_state_machine.router, prefix="/api/zone-state-machine")
app.include_router(uart.router, prefix="/api/uart")
app.include_router(websocket.router)

# ────────────────────────────────────────────────────────────────
# Mount frontend build
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")
