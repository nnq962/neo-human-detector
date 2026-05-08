from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from api.routes import config, detector, websocket

app = FastAPI()

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


app.include_router(config.router,   prefix="/api/config")
app.include_router(detector.router, prefix="/api/detector")
app.include_router(websocket.router)

# Mount frontend build (PHẢI NẰM Ở CUỐI CÙNG ĐỂ KHÔNG CHẶN API VÀ WEBSOCKET)
app.mount("/", StaticFiles(directory="static", html=True), name="frontend")
