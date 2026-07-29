from api.models.reid import ReIdConfig, ReIdConfigUpdate
from api.services import config_store
from src.model_catalog import (
    find_default_model,
    model_id_from_path,
    resolve_model,
)


NESTED_SECTIONS = {"embedding", "track", "quality", "gallery"}


# ─────────────────────────────────────────────────────────────────────────────
def _model_dump(model, **kwargs) -> dict:
    """Chuyển Pydantic model thành dictionary."""
    return model.model_dump(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
def _normalize_reid_config(config: dict) -> dict:
    """Chuẩn hóa ReID config mới và tự ánh xạ model_path cũ."""
    raw_config = dict(config or {})
    model_id = raw_config.get("model_id")
    if not model_id:
        model_id = model_id_from_path(raw_config.get("model_path"), kind="reid")
    if not model_id:
        model_id = find_default_model("reid")

    raw_config["model_id"] = model_id
    return ReIdConfig(**raw_config).model_dump()


# ─────────────────────────────────────────────────────────────────────────────
def _validate_reid_config(config: dict) -> None:
    """Kiểm tra model ReID được chọn tồn tại khi cấu hình yêu cầu."""
    model_id = config.get("model_id")
    if config.get("enabled") and not model_id:
        raise ValueError("Chưa chọn ReID model.")
    if model_id:
        resolve_model(model_id, kind="reid")


# ─────────────────────────────────────────────────────────────────────────────
def get_reid_config() -> dict:
    """Đọc và chuẩn hóa cấu hình ReID hiện tại."""
    config = config_store.get_config_data()

    return _normalize_reid_config(config.get("reid", {}))


# ─────────────────────────────────────────────────────────────────────────────
def update_reid_config(update: ReIdConfigUpdate) -> dict:
    """Cập nhật một phần cấu hình ReID và lưu xuống YAML."""
    update_data = _model_dump(update, exclude_none=True, exclude_unset=True)

    if update_data:
        def mutate(config: dict) -> dict:
            """Áp dụng phần cấu hình ReID cần cập nhật."""
            reid_config = config.setdefault("reid", {})

            for key, value in update_data.items():
                if key in NESTED_SECTIONS:
                    reid_config.setdefault(key, {}).update(value)
                else:
                    reid_config[key] = value

            reid_config = _normalize_reid_config(reid_config)
            _validate_reid_config(reid_config)
            config["reid"] = reid_config
            return reid_config

        return config_store.update_config_data(mutate)

    return get_reid_config()


# ─────────────────────────────────────────────────────────────────────────────
def replace_reid_config(config: ReIdConfig) -> dict:
    """Thay thế toàn bộ cấu hình ReID."""
    reid_config = _normalize_reid_config(_model_dump(config))
    _validate_reid_config(reid_config)

    def mutate(app_config: dict) -> dict:
        """Ghi section ReID đã chuẩn hóa."""
        app_config["reid"] = reid_config
        return reid_config

    return config_store.update_config_data(mutate)


# ─────────────────────────────────────────────────────────────────────────────
def delete_reid_config() -> None:
    """Xóa section ReID khỏi cấu hình YAML."""
    def mutate(app_config: dict) -> None:
        """Loại bỏ section ReID."""
        app_config.pop("reid", None)

    config_store.update_config_data(mutate)
