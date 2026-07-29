from api.models.detection import DetectionConfig, DetectionConfigUpdate
from api.services import config_store
from src.detection.model_registry import (
    find_default_model,
    find_legacy_detection_model,
    validate_model_config,
)


# ─────────────────────────────────────────────────────────────────────────────
def _model_dump(model, **kwargs) -> dict:
    """Chuyển Pydantic model thành dictionary."""
    return model.model_dump(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
def normalize_detection_config(config: dict) -> dict:
    """Chuẩn hóa detection config mới và tự ánh xạ cấu hình cũ."""
    raw_config = dict(config or {})
    model_id = raw_config.get("model_id")
    if not model_id:
        model_id = find_legacy_detection_model(
            str(raw_config.get("task", "pose")),
            str(raw_config.get("model_size", "medium")),
        )
    if not model_id:
        model_id = find_default_model("detection")

    raw_config["model_id"] = model_id
    return DetectionConfig(**raw_config).model_dump()


# ─────────────────────────────────────────────────────────────────────────────
def validate_detection_config(config: dict) -> None:
    """Kiểm tra detection model được chọn tồn tại trong catalog."""
    validate_model_config(config.get("model_id"))


# ─────────────────────────────────────────────────────────────────────────────
def get_detection_config() -> dict:
    """Đọc và chuẩn hóa cấu hình Detection hiện tại."""
    config = config_store.get_config_data()

    return normalize_detection_config(config.get("detection", {}))


# ─────────────────────────────────────────────────────────────────────────────
def update_detection_config(update: DetectionConfigUpdate) -> dict:
    """Cập nhật một phần cấu hình Detection và lưu xuống YAML."""
    update_data = _model_dump(update, exclude_none=True, exclude_unset=True)

    if update_data:
        def mutate(config: dict) -> dict:
            """Áp dụng phần cấu hình Detection cần cập nhật."""
            detection_config = config.setdefault("detection", {})
            detection_config.update(update_data)
            detection_config = normalize_detection_config(detection_config)
            validate_detection_config(detection_config)
            config["detection"] = detection_config
            return detection_config

        return config_store.update_config_data(mutate)

    return get_detection_config()


# ─────────────────────────────────────────────────────────────────────────────
def replace_detection_config(config: DetectionConfig) -> dict:
    """Thay thế toàn bộ cấu hình Detection."""
    detection_config = normalize_detection_config(_model_dump(config))
    validate_detection_config(detection_config)

    def mutate(app_config: dict) -> dict:
        """Ghi section Detection đã chuẩn hóa."""
        app_config["detection"] = detection_config
        return detection_config

    return config_store.update_config_data(mutate)


# ─────────────────────────────────────────────────────────────────────────────
def delete_detection_config() -> dict:
    """Đặt lại Detection theo model mặc định hiện có trong catalog."""
    detection_config = normalize_detection_config({})

    def mutate(app_config: dict) -> dict:
        """Ghi cấu hình Detection mặc định."""
        app_config["detection"] = detection_config
        return detection_config

    return config_store.update_config_data(mutate)
