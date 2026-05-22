from fastapi import APIRouter, HTTPException
from api.models.detector import (
    DetectorConfigUpdate,
    DetectorSettings,
    DetectorSettingsUpdate,
    DetectorStatus,
)
from api.services import detector as detector_service

router = APIRouter()


# ────────────────────────────────────────────────────────────────
# Lấy cấu hình detector trong default.yaml
@router.get("/config", response_model=DetectorSettings)
def get_detector_config():
    """Get auto_start and detector configuration from default.yaml."""
    try:
        return detector_service.get_detector_config()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ────────────────────────────────────────────────────────────────
# Cập nhật một phần cấu hình detector trong default.yaml
@router.patch("/config", response_model=DetectorSettings)
def update_detector_config(settings: DetectorSettingsUpdate):
    """Partially update auto_start and detector configuration in default.yaml."""
    try:
        return detector_service.update_detector_config(settings)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ────────────────────────────────────────────────────────────────
# Ghi đầy đủ cấu hình detector trong default.yaml
@router.put("/config", response_model=DetectorSettings)
def replace_detector_config(settings: DetectorSettings):
    """Replace auto_start and detector configuration in default.yaml."""
    try:
        return detector_service.update_detector_config(DetectorSettingsUpdate(
            auto_start=settings.auto_start,
            detector=DetectorConfigUpdate(**settings.detector.model_dump()),
        ))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
