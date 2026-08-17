"""Tương thích API detection với catalog model động."""

from __future__ import annotations

from src.model_catalog import (
    ModelArtifact,
    find_default_model,
    find_legacy_detection_model,
    list_models,
    resolve_model,
    resolve_model_path as resolve_catalog_model_path,
)


# ─────────────────────────────────────────────────────────────────────────────
def resolve_model_path(model_id: str) -> str:
    """Phân giải model_id detection thành đường dẫn model tuyệt đối."""
    return resolve_catalog_model_path(model_id, kind="detection")


# ─────────────────────────────────────────────────────────────────────────────
def resolve_model_artifact(model_id: str) -> ModelArtifact:
    """Phân giải model_id thành metadata detection đầy đủ."""
    return resolve_model(model_id, kind="detection")


# ─────────────────────────────────────────────────────────────────────────────
def validate_model_config(model_id: str | None) -> None:
    """Kiểm tra model_id đã chọn tồn tại trong catalog detection."""
    if not model_id:
        raise ValueError("Chưa chọn detection model.")
    resolve_model_artifact(model_id)


# ─────────────────────────────────────────────────────────────────────────────
def supported_models() -> tuple[ModelArtifact, ...]:
    """Trả toàn bộ detection model hiện có trong thư mục weights."""
    return list_models("detection")


__all__ = [
    "find_default_model",
    "find_legacy_detection_model",
    "resolve_model_artifact",
    "resolve_model_path",
    "supported_models",
    "validate_model_config",
]
