from fastapi import APIRouter, HTTPException, Response
from api.models.config import AppConfig
from api.services import config as config_service
from utils import LOGGER

router = APIRouter()

# ────────────────────────────────────────────────────────────────
# Lấy config
@router.get("", response_model=AppConfig)
def get_config():
    """Retrieve the current configuration from default.yaml."""
    try:
        return config_service.get_config_data()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

# ────────────────────────────────────────────────────────────────
# Cập nhật config
@router.put("", response_model=dict)
def update_config(config: AppConfig):
    """Partially or fully update the configuration in default.yaml."""
    try:
        current_config = config_service.get_config_data()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Lấy những trường mà người dùng THỰC SỰ gởi lên (bỏ qua giá trị mặc định của pydantic)
    update_data = config.model_dump(exclude_unset=True)
    
    # Merge data mới đè lên file hiện tại
    merged_config = config_service.deep_update(current_config, update_data)
    
    # Validate lại cấu trúc một lần nữa cho chuẩn
    try:
        final_config = AppConfig(**merged_config).model_dump()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Validation error: {e}")
    
    try:
        config_service.save_config_data(final_config)
        return {"status": "success", "message": "Configuration updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save configuration: {e}")

# ────────────────────────────────────────────────────────────────
# Lấy hình ảnh từ webcam
@router.get("/get-snapshot")
def get_snapshot():
    try:
        buffer = config_service.get_snapshot_image()
        return Response(content=buffer, media_type="image/jpeg")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))