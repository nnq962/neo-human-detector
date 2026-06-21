"""
Config dataclasses cho Runtime, tương ứng với từng section trong YAML.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.reid import ReIdConfig


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DetectionConfig:
    """Section [detection] trong YAML."""

    task       : str   = "pose"           # "detect" hoặc "pose"
    model_size : str   = "nano"
    batch_size : int   = 1
    conf       : float = 0.5
    tracker    : str   = "bytetrack.yaml"
    persist    : bool  = True
    verbose    : bool  = True


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class PreviewConfig:
    """Section [preview] trong YAML."""

    enabled: bool  = True
    scale  : float = 1.0


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ZoneStateMachineConfig:
    """Section [zone_state_machine] trong YAML."""

    confirm_enter_time      : float = 8.0
    confirm_exit_time       : float = 8.0
    pending_enter_miss_grace: float = 1.5


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RuntimeConfig:
    """Config tổng hợp cho Runtime."""

    config_path       : str                    = "configs/test.yaml"
    detection         : DetectionConfig        = field(default_factory=DetectionConfig)
    preview           : PreviewConfig          = field(default_factory=PreviewConfig)
    zone_state_machine: ZoneStateMachineConfig = field(default_factory=ZoneStateMachineConfig)
    reid              : ReIdConfig             = field(default_factory=ReIdConfig)
