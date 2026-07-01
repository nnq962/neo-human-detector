"""
Module sinh request robot từ dữ liệu runtime.
"""

from src.robot_dispatch.datatypes import (
    PersonServiceRecord,
    PersonServiceState,
    RobotDispatchConfig,
    RobotDispatchEvent,
    RobotDispatchRequest,
    build_zone_dispatch_request,
)
from src.robot_dispatch.dispatcher import RobotDispatcher
from src.robot_dispatch.event_store import RobotDispatchEventStore, robot_dispatch_events
from src.robot_dispatch.transport import (
    InMemoryRobotTransport,
    LoggingRobotTransport,
    RobotTransport,
)
from src.robot_dispatch.uart_transport import UartRobotTransport, build_uart_dispatch_payload

__all__ = [
    "InMemoryRobotTransport",
    "LoggingRobotTransport",
    "PersonServiceRecord",
    "PersonServiceState",
    "RobotDispatchConfig",
    "RobotDispatchEvent",
    "RobotDispatchEventStore",
    "RobotDispatchRequest",
    "RobotDispatcher",
    "RobotTransport",
    "UartRobotTransport",
    "build_uart_dispatch_payload",
    "build_zone_dispatch_request",
    "robot_dispatch_events",
]
