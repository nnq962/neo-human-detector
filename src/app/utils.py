"""
Build functions cho mỗi config section trong Runtime.
"""

from __future__ import annotations

from typing import Optional

from src.app.datatypes import (
    DetectionConfig,
    PreviewConfig,
    RuntimeConfig,
    ZoneStateMachineConfig,
)
from src.reid import ReIdConfig
from src.robot_dispatch_v2 import RobotDispatchV2Config
from utils import load_config


# ─────────────────────────────────────────────────────────────────────────────
def build_detection_config(raw: dict) -> DetectionConfig:
    return DetectionConfig(
        task       = str(raw.get("task", "pose")),
        model_size = str(raw.get("model_size", "nano")),
        batch_size = int(raw.get("batch_size", 1)),
        conf       = float(raw.get("conf", 0.5)),
        verbose    = bool(raw.get("verbose", False)),
    )


# ─────────────────────────────────────────────────────────────────────────────
def build_preview_config(raw: dict, *, show: Optional[bool] = None) -> PreviewConfig:
    return PreviewConfig(
        enabled       = bool(raw.get("enabled", False)) if show is None else show,
        window_width  = int(raw.get("window_width", 1280)),
        window_height = int(raw.get("window_height", 720)),
    )


# ─────────────────────────────────────────────────────────────────────────────
def build_zone_state_machine_config(raw: dict) -> ZoneStateMachineConfig:
    return ZoneStateMachineConfig(
        confirm_enter_time       = float(raw.get("confirm_enter_time", 8.0)),
        confirm_exit_time        = float(raw.get("confirm_exit_time", 8.0)),
        pending_enter_miss_grace_time = float(raw.get("pending_enter_miss_grace_time", 1.5)),
    )


# ─────────────────────────────────────────────────────────────────────────────
def build_reid_config(raw: dict) -> ReIdConfig:
    emb     = raw.get("embedding", {})
    track   = raw.get("track", {})
    quality = raw.get("quality", {})
    gallery = raw.get("gallery", {})

    return ReIdConfig(
        enabled                   = bool(raw.get("enabled", False)),
        zone_only                 = bool(raw.get("zone_only", True)),
        require_occupied_zone     = bool(raw.get("require_occupied_zone", True)),
        model_path                = raw.get("model_path"),
        device                    = str(raw.get("device", "auto")),
        embedding_batch_size      = int(emb.get("batch_size", 32)),
        buffer_min                = int(track.get("buffer_min", 200)),
        grace_period              = int(track.get("grace_period", 20)),
        update_interval           = int(track.get("update_interval", 120)),
        max_buffer_size           = int(track.get("max_buffer_size", 250)),
        gallery_cleanup_interval  = int(track.get("gallery_cleanup_interval", 1800)),
        max_reverify_misses       = int(track.get("max_reverify_misses", 3)),
        overlap_iou_threshold     = float(quality.get("overlap_iou_threshold", 0.25)),
        overlap_ioa_threshold     = float(quality.get("overlap_ioa_threshold", 0.45)),
        stable_bbox_window        = int(quality.get("stable_bbox_window", 100)),
        stable_center_shift_ratio = float(quality.get("stable_center_shift_ratio", 0.20)),
        stable_size_change_ratio  = float(quality.get("stable_size_change_ratio", 0.25)),
        laplacian_var_threshold   = float(quality.get("laplacian_var_threshold", 50.0)),
        sim_threshold_match       = float(gallery.get("sim_threshold_match", 0.85)),
        ema_alpha                 = float(gallery.get("ema_alpha", 0.75)),
        max_samples               = int(gallery.get("max_samples", 5)),
        gallery_ttl_minutes       = float(gallery.get("ttl_minutes", 2.0)),
    )


# ─────────────────────────────────────────────────────────────────────────────
def build_robot_dispatch_config(raw: dict) -> RobotDispatchV2Config:
    """Đọc section robot_dispatch và tạo config cho RobotDispatcherV2."""
    return RobotDispatchV2Config(
        enabled=bool(raw.get("enabled", False)),
        use_reid=bool(raw.get("use_reid", False)),
        ack_timeout_seconds=float(raw.get("ack_timeout_seconds", 1.0)),
        max_retries=int(raw.get("max_retries", 5)),
    )


# ─────────────────────────────────────────────────────────────────────────────
def build_runtime_config(
    config_path: str = "configs/test.yaml",
    *,
    show: Optional[bool] = None,
) -> RuntimeConfig:
    """Đọc YAML và tạo RuntimeConfig đầy đủ."""
    cfg = load_config(config_path)
    return RuntimeConfig(
        config_path        = config_path,
        detection          = build_detection_config(cfg.get("detection", {})),
        preview            = build_preview_config(cfg.get("preview", {}), show=show),
        zone_state_machine = build_zone_state_machine_config(cfg.get("zone_state_machine", {})),
        reid               = build_reid_config(cfg.get("reid", {})),
        robot_dispatch     = build_robot_dispatch_config(cfg.get("robot_dispatch", {})),
    )
