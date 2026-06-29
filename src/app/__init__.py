"""
Package app — Runtime và config.
"""

from src.app.datatypes import (
    DetectionConfig,
    PreviewConfig,
    RuntimeConfig,
    ZoneStateMachineConfig,
)
from src.app.runtime import Runtime, run
from src.app.utils import (
    build_detection_config,
    build_preview_config,
    build_reid_config,
    build_robot_dispatch_config,
    build_runtime_config,
    build_zone_state_machine_config,
)

__all__ = [
    # config dataclasses
    "DetectionConfig",
    "PreviewConfig",
    "RuntimeConfig",
    "ZoneStateMachineConfig",
    # runtime
    "Runtime",
    "run",
    # builders
    "build_detection_config",
    "build_preview_config",
    "build_reid_config",
    "build_robot_dispatch_config",
    "build_runtime_config",
    "build_zone_state_machine_config",
]
