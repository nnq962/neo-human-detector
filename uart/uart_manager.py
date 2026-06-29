from __future__ import annotations

from collections import deque
import copy
import json
import os
import threading
import time
from typing import Any, Callable, Optional

import serial

from utils import LOGGER, load_config


DEFAULT_PORT = "/dev/ttyS4"
DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT = 1
DEFAULT_EVENT_BUFFER_SIZE = 1000
CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "configs/default.yaml",
)


# ─────────────────────────────────────────────────────────────────────────────
class UartManager:
    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
        event_buffer_size: int = DEFAULT_EVENT_BUFFER_SIZE,
    ):
        """Khởi tạo manager UART nhưng chưa mở cổng serial."""
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn: Optional[serial.Serial] = None

        self.latest_received_data: Optional[dict] = None
        self.latest_received_event: Optional[dict] = None
        self.is_listening = False
        self.listen_thread: Optional[threading.Thread] = None
        self.last_error: Optional[str] = None
        self.last_connected_at: Optional[float] = None
        self.last_disconnected_at: Optional[float] = None
        self.last_received_at: Optional[float] = None
        self._events = deque(maxlen=event_buffer_size)
        self._event_sequence = 0
        self._sync_handler: Optional[Callable[[Optional[dict]], None]] = None

        self._lock = threading.RLock()

    # ─────────────────────────────────────────────────────────────────────────
    def connect(self) -> bool:
        """Mở cổng Serial và khởi động thread lắng nghe nếu thành công."""
        with self._lock:
            if self._is_connected_unlocked():
                return True

            if not self._open_serial_unlocked():
                return False

        self.start_listening()
        return True

    # ─────────────────────────────────────────────────────────────────────────
    def start_listening(self) -> None:
        """Khởi động luồng nền đọc dữ liệu UART."""
        with self._lock:
            if self.is_listening:
                return

            self.is_listening = True
            self.listen_thread = threading.Thread(
                target=self._listen_loop,
                daemon=True,
                name="uart-listener",
            )
            self.listen_thread.start()
            LOGGER.info("Đã khởi động luồng lắng nghe UART.")

    # ─────────────────────────────────────────────────────────────────────────
    def stop_listening(self) -> None:
        """Dừng luồng lắng nghe UART."""
        with self._lock:
            self.is_listening = False
            thread = self.listen_thread

        if (
            thread
            and thread.is_alive()
            and threading.current_thread() is not thread
        ):
            thread.join(timeout=2)

        with self._lock:
            if self.listen_thread is thread:
                self.listen_thread = None

    # ─────────────────────────────────────────────────────────────────────────
    def disconnect(self) -> None:
        """Dừng lắng nghe và đóng cổng Serial hiện tại."""
        self.stop_listening()
        self._close_serial()

    # ─────────────────────────────────────────────────────────────────────────
    def request_reconnect(self) -> bool:
        """Đóng cổng hiện tại nếu cần rồi thử kết nối lại."""
        self._close_serial()
        return self.connect()

    # ─────────────────────────────────────────────────────────────────────────
    def reconfigure(
        self,
        port: Optional[str] = None,
        baudrate: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> bool:
        """Cập nhật cấu hình UART và khởi động lại kết nối nếu cần."""
        with self._lock:
            next_port = port or self.port
            next_baudrate = baudrate if baudrate is not None else self.baudrate
            next_timeout = timeout if timeout is not None else self.timeout
            unchanged = (
                next_port == self.port
                and next_baudrate == self.baudrate
                and next_timeout == self.timeout
            )

        if unchanged:
            if self.is_connected():
                LOGGER.info("UART config unchanged, skip reconnect.")
                return True

            LOGGER.info("UART config unchanged but disconnected, retry connect.")
            return self.connect()

        self.disconnect()
        with self._lock:
            self.port = next_port
            self.baudrate = next_baudrate
            self.timeout = next_timeout

        LOGGER.info(f"Đang khởi động lại UART với port={self.port}, baudrate={self.baudrate}")
        return self.connect()

    # ─────────────────────────────────────────────────────────────────────────
    def send_json(self, data_dict: dict) -> bool:
        """Đóng gói Dictionary thành JSON và gửi đi."""
        return self.send_string(json.dumps(data_dict))

    # ─────────────────────────────────────────────────────────────────────────
    def send_string(self, text_str: str) -> bool:
        """Gửi chuỗi thuần qua UART."""
        if not text_str.endswith("\n"):
            text_str += "\n"

        with self._lock:
            conn = self.serial_conn
            if conn is None or not conn.is_open:
                LOGGER.error("Cổng UART chưa mở.")
                return False

            try:
                conn.write(text_str.encode("utf-8"))
                # LOGGER.info(f"Send: {text_str.strip()}")
                return True
            except Exception as e:
                self.last_error = str(e)
                LOGGER.error(f"Lỗi khi gửi: {e}")
                return False

    # ─────────────────────────────────────────────────────────────────────────
    def receive_data(self) -> Any:
        """Đọc và tự động phân tích dữ liệu trả về từ ESP32."""
        event = self.receive_event()
        if event is None:
            return None

        self._handle_received_event(event)
        return event["data"]

    # ─────────────────────────────────────────────────────────────────────────
    def receive_event(self) -> Optional[dict]:
        """Đọc một dòng UART và chuẩn hóa thành event JSON/string."""
        with self._lock:
            conn = self.serial_conn
            if conn is None or not conn.is_open:
                return None

            try:
                if conn.in_waiting <= 0:
                    return None
                raw_data = conn.readline().decode("utf-8", errors="ignore").strip()
            except Exception as e:
                self.last_error = str(e)
                LOGGER.error(f"Lỗi khi đọc: {e}")
                return None

        if not raw_data:
            return None

        try:
            parsed_data = json.loads(raw_data)
            # LOGGER.info(f"Recv: {parsed_data}")
            return {
                "type": "json",
                "raw": raw_data,
                "data": parsed_data,
            }
        except json.JSONDecodeError:
            # LOGGER.info(f"Recv: {raw_data}")
            return {
                "type": "string",
                "raw": raw_data,
                "data": raw_data,
            }

    # ─────────────────────────────────────────────────────────────────────────
    def get_latest_received_data(self) -> Optional[dict]:
        """Trả bản copy dữ liệu UART mới nhất để websocket đọc an toàn."""
        with self._lock:
            return copy.deepcopy(self.latest_received_data)

    # ─────────────────────────────────────────────────────────────────────────
    def get_latest_received_event(self) -> Optional[dict]:
        """Trả bản copy event UART mới nhất."""
        with self._lock:
            return copy.deepcopy(self.latest_received_event)

    # ─────────────────────────────────────────────────────────────────────────
    def get_event_sequence(self) -> int:
        """Trả sequence mới nhất để client bắt đầu nghe event mới."""
        with self._lock:
            return self._event_sequence

    # ─────────────────────────────────────────────────────────────────────────
    def get_events_after(self, sequence: int, limit: int = 100) -> list[dict]:
        """Trả các event có sequence lớn hơn sequence đã biết."""
        with self._lock:
            events = [
                event
                for event in self._events
                if event["sequence"] > sequence
            ]

        return copy.deepcopy(events[:limit])

    # ─────────────────────────────────────────────────────────────────────────
    def status(self) -> dict:
        """Trả trạng thái runtime của UART manager."""
        with self._lock:
            return {
                "port": self.port,
                "baudrate": self.baudrate,
                "timeout": self.timeout,
                "connected": self._is_connected_unlocked(),
                "is_listening": self.is_listening,
                "last_error": self.last_error,
                "last_connected_at": self.last_connected_at,
                "last_disconnected_at": self.last_disconnected_at,
                "last_received_at": self.last_received_at,
                "last_event_sequence": self._event_sequence,
                "event_buffer_size": self._events.maxlen,
            }

    # ─────────────────────────────────────────────────────────────────────────
    def set_sync_handler(self, handler: Optional[Callable[[Optional[dict]], None]]) -> None:
        """Đăng ký callback xử lý khi robot gửi lệnh sync."""
        with self._lock:
            self._sync_handler = handler

    # ─────────────────────────────────────────────────────────────────────────
    def is_connected(self) -> bool:
        with self._lock:
            return self._is_connected_unlocked()

    # ─────────────────────────────────────────────────────────────────────────
    def close(self) -> None:
        """Đóng kết nối an toàn."""
        self.disconnect()

    # ─────────────────────────────────────────────────────────────────────────
    def _listen_loop(self) -> None:
        """Vòng lặp nền liên tục đọc UART."""
        while True:
            with self._lock:
                if not self.is_listening:
                    return
                connected = self._is_connected_unlocked()

            if not connected:
                LOGGER.warning("Mất kết nối UART, đang thử kết nối lại...")
                time.sleep(2)
                with self._lock:
                    if not self.is_listening:
                        return

                    self._close_serial_unlocked()
                    self._open_serial_unlocked()
                continue

            self.receive_data()

            time.sleep(0.01)

    # ─────────────────────────────────────────────────────────────────────────
    def _handle_received_data(self, data: Any) -> None:
        event_type = "string" if isinstance(data, str) else "json"
        event = {
            "type": event_type,
            "raw": json.dumps(data) if event_type == "json" else str(data),
            "data": data,
        }
        self._handle_received_event(event)

    # ─────────────────────────────────────────────────────────────────────────
    def _handle_received_event(self, event: dict) -> None:
        now = time.time()
        event = {
            "sequence": None,
            "timestamp": now,
            **event,
        }

        with self._lock:
            self._event_sequence += 1
            event["sequence"] = self._event_sequence
            self.last_received_at = now
            self.latest_received_event = event
            self._events.append(event)

            if event["type"] == "json" and isinstance(event["data"], dict):
                self.latest_received_data = {
                    "timestamp": now,
                    "payload": event["data"],
                }

        if event["type"] == "string" and str(event["data"]).strip() == "sync":
            self._handle_sync_command()

    # ─────────────────────────────────────────────────────────────────────────
    def _handle_sync_command(self) -> None:
        """Gọi callback sync hiện tại nếu runtime đã đăng ký."""
        with self._lock:
            handler = self._sync_handler
            latest_received_data = copy.deepcopy(self.latest_received_data)

        if handler is None:
            LOGGER.info("Nhận lệnh sync nhưng chưa có runtime đăng ký handler.")
            return

        try:
            handler(latest_received_data)
        except Exception as e:
            self.last_error = str(e)
            LOGGER.error(f"Lỗi khi xử lý lệnh sync: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    def _close_serial(self) -> None:
        with self._lock:
            self._close_serial_unlocked()

    # ─────────────────────────────────────────────────────────────────────────
    def _open_serial_unlocked(self) -> bool:
        try:
            self.serial_conn = serial.Serial(
                self.port,
                self.baudrate,
                timeout=self.timeout,
            )
            self.last_error = None
            self.last_connected_at = time.time()
            LOGGER.info(f"Đã kết nối UART tại {self.port}")
            return True
        except (serial.SerialException, ValueError, OSError) as e:
            self.serial_conn = None
            self.last_error = str(e)
            LOGGER.error(f"Lỗi mở cổng {self.port}: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────────
    def _close_serial_unlocked(self) -> None:
        conn = self.serial_conn
        self.serial_conn = None

        if conn is not None and conn.is_open:
            try:
                conn.close()
                LOGGER.info("Đã ngắt kết nối UART.")
            except Exception as e:
                self.last_error = str(e)
                LOGGER.error(f"Lỗi khi đóng UART: {e}")

        self.last_disconnected_at = time.time()

    # ─────────────────────────────────────────────────────────────────────────
    def _is_connected_unlocked(self) -> bool:
        return self.serial_conn is not None and self.serial_conn.is_open


# ─────────────────────────────────────────────────────────────────────────────
def _load_uart_config() -> dict:
    try:
        config = load_config(CONFIG_FILE)
    except Exception as e:
        LOGGER.error(f"Không thể load UART config: {e}")
        return {}

    uart_cfg = config.get("uart", {})
    return uart_cfg if isinstance(uart_cfg, dict) else {}


# ─────────────────────────────────────────────────────────────────────────────
def create_uart_manager_from_config(*, connect: bool = False) -> UartManager:
    uart_cfg = _load_uart_config()
    manager = UartManager(
        port=uart_cfg.get("port", DEFAULT_PORT),
        baudrate=uart_cfg.get("baudrate", DEFAULT_BAUDRATE),
        timeout=DEFAULT_TIMEOUT,
    )

    if connect:
        manager.connect()

    return manager


# ─────────────────────────────────────────────────────────────────────────────
uart_manager = create_uart_manager_from_config(connect=False)
