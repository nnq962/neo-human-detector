from fastapi import APIRouter, HTTPException
from api.models.detector import DetectorStatus
from api.services import detector as detector_service

router = APIRouter()

# ────────────────────────────────────────────────────────────────
# Lấy trạng thái detector
@router.get("/status", response_model=DetectorStatus)
def get_status():
    """Get current detector status."""
    return detector_service.get_status()

# ────────────────────────────────────────────────────────────────
# Khởi động detector
@router.post("/start", response_model=dict)
def start():
    """Start the detector using current configuration."""
    try:
        return detector_service.start()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

# ────────────────────────────────────────────────────────────────
# Dừng detector
@router.post("/stop", response_model=dict)
def stop():
    """Stop the running detector."""
    return detector_service.stop()

# ────────────────────────────────────────────────────────────────
# Restart detector (load lại config mới nhất)
@router.post("/restart", response_model=dict)
def restart():
    """Stop and restart the detector with latest configuration."""
    try:
        detector_service.stop()
        return detector_service.start()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))