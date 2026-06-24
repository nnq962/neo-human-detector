from typing import Literal, Optional

from pydantic import BaseModel, Field


class ReIdEmbeddingConfig(BaseModel):
    batch_size: int = Field(32, ge=1)


class ReIdEmbeddingConfigUpdate(BaseModel):
    batch_size: Optional[int] = Field(None, ge=1)


class ReIdTrackConfig(BaseModel):
    buffer_min: int = Field(200, ge=1)
    grace_period: int = Field(20, ge=0)
    update_interval: int = Field(120, ge=1)
    max_buffer_size: int = Field(250, ge=1)
    gallery_cleanup_interval: int = Field(1800, ge=1)
    max_reverify_misses: int = Field(3, ge=0)


class ReIdTrackConfigUpdate(BaseModel):
    buffer_min: Optional[int] = Field(None, ge=1)
    grace_period: Optional[int] = Field(None, ge=0)
    update_interval: Optional[int] = Field(None, ge=1)
    max_buffer_size: Optional[int] = Field(None, ge=1)
    gallery_cleanup_interval: Optional[int] = Field(None, ge=1)
    max_reverify_misses: Optional[int] = Field(None, ge=0)


class ReIdQualityConfig(BaseModel):
    overlap_iou_threshold: float = Field(0.25, ge=0.0, le=1.0)
    overlap_ioa_threshold: float = Field(0.45, ge=0.0, le=1.0)
    stable_bbox_window: int = Field(100, ge=1)
    stable_center_shift_ratio: float = Field(0.20, ge=0.0)
    stable_size_change_ratio: float = Field(0.25, ge=0.0)
    laplacian_var_threshold: float = Field(50.0, ge=0.0)


class ReIdQualityConfigUpdate(BaseModel):
    overlap_iou_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    overlap_ioa_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    stable_bbox_window: Optional[int] = Field(None, ge=1)
    stable_center_shift_ratio: Optional[float] = Field(None, ge=0.0)
    stable_size_change_ratio: Optional[float] = Field(None, ge=0.0)
    laplacian_var_threshold: Optional[float] = Field(None, ge=0.0)


class ReIdGalleryConfig(BaseModel):
    sim_threshold_match: float = Field(0.85, ge=0.0, le=1.0)
    ema_alpha: float = Field(0.75, ge=0.0, le=1.0)
    max_samples: int = Field(5, ge=1)
    ttl_minutes: float = Field(2.0, ge=0.0)


class ReIdGalleryConfigUpdate(BaseModel):
    sim_threshold_match: Optional[float] = Field(None, ge=0.0, le=1.0)
    ema_alpha: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_samples: Optional[int] = Field(None, ge=1)
    ttl_minutes: Optional[float] = Field(None, ge=0.0)


class ReIdConfig(BaseModel):
    enabled: bool = False
    zone_only: bool = True
    require_occupied_zone: bool = True
    model_path: Optional[str] = None
    device: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    embedding: ReIdEmbeddingConfig = Field(default_factory=ReIdEmbeddingConfig)
    track: ReIdTrackConfig = Field(default_factory=ReIdTrackConfig)
    quality: ReIdQualityConfig = Field(default_factory=ReIdQualityConfig)
    gallery: ReIdGalleryConfig = Field(default_factory=ReIdGalleryConfig)


class ReIdConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    zone_only: Optional[bool] = None
    require_occupied_zone: Optional[bool] = None
    model_path: Optional[str] = None
    device: Optional[Literal["auto", "cpu", "cuda", "mps"]] = None
    embedding: Optional[ReIdEmbeddingConfigUpdate] = None
    track: Optional[ReIdTrackConfigUpdate] = None
    quality: Optional[ReIdQualityConfigUpdate] = None
    gallery: Optional[ReIdGalleryConfigUpdate] = None
