import sys
import types

from src.app.datatypes import RuntimeConfig
from src.app.runtime import Runtime
from src.app.utils import build_robot_dispatch_config
from src.reid import ReIdConfig
from src.robot_dispatch_v2 import RobotDispatchV2Config, RobotDispatcherV2


# ─────────────────────────────────────────────────────────────────────────────
class FakeUartManagerV2:
    """UART manager giả để kiểm tra lifecycle Runtime mà không mở serial thật."""

    def __init__(self) -> None:
        self.reconfigure_calls = []
        self.additional_handlers = {}
        self.closed = False

    def reconfigure(self, *, port=None, baudrate=None) -> bool:
        self.reconfigure_calls.append((port, baudrate))
        return True

    def connect(self) -> bool:
        return True

    def close(self) -> None:
        self.closed = True

    def set_handler(self, message_type, handler) -> None:
        pass

    def add_handler(self, message_type, handler) -> None:
        handlers = self.additional_handlers.setdefault(int(message_type), [])
        if handler not in handlers:
            handlers.append(handler)

    def remove_handler(self, message_type, handler) -> None:
        handlers = self.additional_handlers.get(int(message_type), [])
        if handler in handlers:
            handlers.remove(handler)

    def send_message(self, message) -> bool:
        return True

    def send_with_retry(
        self,
        message,
        task_id: int,
        timeout: float = 1.0,
        max_retries: int = 5,
    ) -> bool:
        return True


# ─────────────────────────────────────────────────────────────────────────────
def test_build_robot_dispatch_config_uses_v2_fields() -> None:
    config = build_robot_dispatch_config(
        {
            "enabled": True,
            "use_reid": True,
            "ack_timeout_seconds": 0.75,
            "max_retries": 3,
        }
    )

    assert config == RobotDispatchV2Config(
        enabled=True,
        use_reid=True,
        ack_timeout_seconds=0.75,
        max_retries=3,
    )


# ─────────────────────────────────────────────────────────────────────────────
def test_runtime_builds_v2_dispatcher_without_closing_shared_uart() -> None:
    fake_uart = FakeUartManagerV2()
    fake_module = types.ModuleType("uart_v2.uart_manager")
    fake_module.uart_manager_v2 = fake_uart
    previous_module = sys.modules.get("uart_v2.uart_manager")
    sys.modules["uart_v2.uart_manager"] = fake_module

    runtime = Runtime(
        RuntimeConfig(
            robot_dispatch=RobotDispatchV2Config(
                enabled=True,
                ack_timeout_seconds=0.5,
                max_retries=2,
            )
        )
    )

    try:
        dispatcher = runtime._build_robot_dispatcher(
            {
                "uart": {
                    "port": "/tmp/tty-test",
                    "baudrate": 115200,
                }
            }
        )
        runtime.robot_dispatcher = dispatcher

        assert isinstance(dispatcher, RobotDispatcherV2)
        assert not dispatcher.decision_engine.uses_reid
        assert fake_uart.reconfigure_calls == [("/tmp/tty-test", 115200)]
        assert sum(len(items) for items in fake_uart.additional_handlers.values()) == 2

        runtime.stop()

        assert not fake_uart.closed
        assert sum(len(items) for items in fake_uart.additional_handlers.values()) == 0
        assert runtime.robot_dispatcher is None
        assert runtime._robot_uart is fake_uart
    finally:
        if previous_module is None:
            sys.modules.pop("uart_v2.uart_manager", None)
        else:
            sys.modules["uart_v2.uart_manager"] = previous_module


# ────────────────────────────────────────────────────────────────────
def test_runtime_builds_reid_decision_engine_when_enabled() -> None:
    fake_uart = FakeUartManagerV2()
    fake_module = types.ModuleType("uart_v2.uart_manager")
    fake_module.uart_manager_v2 = fake_uart
    previous_module = sys.modules.get("uart_v2.uart_manager")
    sys.modules["uart_v2.uart_manager"] = fake_module

    runtime = Runtime(
        RuntimeConfig(
            reid=ReIdConfig(enabled=True),
            robot_dispatch=RobotDispatchV2Config(enabled=True, use_reid=True),
        )
    )

    try:
        dispatcher = runtime._build_robot_dispatcher({"uart": {}})
        runtime.robot_dispatcher = dispatcher

        assert dispatcher.decision_engine.uses_reid
    finally:
        runtime.stop()
        if previous_module is None:
            sys.modules.pop("uart_v2.uart_manager", None)
        else:
            sys.modules["uart_v2.uart_manager"] = previous_module


# ────────────────────────────────────────────────────────────────────────
def test_runtime_rejects_reid_dispatch_when_reid_pipeline_is_disabled() -> None:
    runtime = Runtime(
        RuntimeConfig(
            robot_dispatch=RobotDispatchV2Config(enabled=True, use_reid=True),
        )
    )

    try:
        runtime._build_robot_dispatcher({})
    except ValueError as exc:
        assert "reid.enabled=true" in str(exc)
    else:
        raise AssertionError("Runtime phải từ chối cấu hình ReID không nhất quán")
