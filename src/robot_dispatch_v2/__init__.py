"""Điều phối robot qua giao thức nhị phân V2."""

from src.robot_dispatch_v2.config import RobotDispatchV2Config
from src.robot_dispatch_v2.dispatcher import RobotDispatcherV2
from src.robot_dispatch_v2.robot_state import RobotSnapshot, RobotStateStore
from src.robot_dispatch_v2.task_registry import (
    AssignedTask,
    TaskRegistry,
    TaskRegistryFull,
)

__all__ = [
    "AssignedTask",
    "RobotDispatchV2Config",
    "RobotDispatcherV2",
    "RobotSnapshot",
    "RobotStateStore",
    "TaskRegistry",
    "TaskRegistryFull",
]
