"""Đọc, kiểm tra và lưu cấu hình auto-dispatch robot."""

from __future__ import annotations

from api.models.robot_dispatch import RobotDispatchConfig, RobotDispatchConfigUpdate
from api.services import config_store


# ─────────────────────────────────────────────────────────────────────────────
def _model_dump(model, **kwargs) -> dict:
    """Chuyển Pydantic model thành dictionary."""
    return model.model_dump(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
def _normalize_robot_dispatch_config(config: dict | None) -> dict:
    """Chuẩn hóa section robot_dispatch bằng các giá trị mặc định an toàn."""
    return RobotDispatchConfig(**(config or {})).model_dump()


# ─────────────────────────────────────────────────────────────────────────────
def _validate_robot_dispatch_config(config: dict, app_config: dict) -> None:
    """Kiểm tra auto-dispatch ReID chỉ bật khi ReID ứng dụng đang hoạt động."""
    if (
        config["enabled"]
        and config["use_reid"]
        and not (app_config.get("reid") or {}).get("enabled")
    ):
        raise ValueError("Bật dùng ReID cho robot yêu cầu ReID đang được bật.")


# ─────────────────────────────────────────────────────────────────────────────
def get_robot_dispatch_config() -> dict:
    """Đọc cấu hình auto-dispatch robot hiện tại."""
    app_config = config_store.get_config_data()
    return _normalize_robot_dispatch_config(app_config.get("robot_dispatch"))


# ─────────────────────────────────────────────────────────────────────────────
def update_robot_dispatch_config(update: RobotDispatchConfigUpdate) -> dict:
    """Cập nhật một phần robot_dispatch rồi lưu xuống YAML."""
    update_data = _model_dump(update, exclude_none=True, exclude_unset=True)
    if not update_data:
        return get_robot_dispatch_config()

    def mutate(app_config: dict) -> dict:
        """Áp dụng, chuẩn hóa và kiểm tra cấu hình mới trong một transaction."""
        current = _normalize_robot_dispatch_config(app_config.get("robot_dispatch"))
        normalized = _normalize_robot_dispatch_config({**current, **update_data})
        _validate_robot_dispatch_config(normalized, app_config)
        app_config["robot_dispatch"] = normalized
        return normalized

    return config_store.update_config_data(mutate)


# ─────────────────────────────────────────────────────────────────────────────
def replace_robot_dispatch_config(config: RobotDispatchConfig) -> dict:
    """Thay thế toàn bộ cấu hình auto-dispatch robot."""
    normalized = _normalize_robot_dispatch_config(_model_dump(config))

    def mutate(app_config: dict) -> dict:
        """Kiểm tra và ghi đè section robot_dispatch."""
        _validate_robot_dispatch_config(normalized, app_config)
        app_config["robot_dispatch"] = normalized
        return normalized

    return config_store.update_config_data(mutate)
