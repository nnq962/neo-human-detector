from __future__ import annotations

import copy
import os
import struct
import threading
import time
from typing import Callable, Optional

import serial

from utils import LOGGER, load_config
from src.robot_dispatch_v2.datatypes import MessageBase, MessageType


DEFAULT_PORT = "/dev/ttyS4"
DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT = 1
CRC_SIZE = 2  # số byte checksum (crc32(payload) & 0xFFFF), khớp struct.pack('<H', crc) trong MessageBase.encode()
ACK_TTL = 30.0  # giây; ACK không ai wait_for_ack() nhận trong khoảng này sẽ bị dọn khỏi _received_acks
BINARY_START_BYTE = 0xAA  # byte đánh dấu đầu mỗi gói nhị phân
CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "configs/default.yaml",
)


# ─────────────────────────────────────────────────────────────────────────────
class UartManagerV2:
    """
    Phiên bản UART manager chỉ xử lý giao thức nhị phân (không còn JSON/string).

    Khung mỗi gói tin trên dây (wire format):
        [BINARY_START_BYTE][payload theo FORMAT của message][checksum]
                1 byte              N byte (tùy loại message)      2 byte

    Vì mỗi loại message có kích thước CỐ ĐỊNH (tra qua MessageBase._registry),
    bên nhận không cần dấu kết thúc kiểu '\\n' như bản JSON/string cũ - chỉ cần
    biết message_type là biết chính xác cần đọc thêm bao nhiêu byte.
    """

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """Khởi tạo manager UART nhưng chưa mở cổng serial."""
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn: Optional[serial.Serial] = None

        self.latest_received_message: Optional[MessageBase] = None
        self.is_listening = False
        self.listen_thread: Optional[threading.Thread] = None
        self.last_error: Optional[str] = None
        self.last_connected_at: Optional[float] = None
        self.last_disconnected_at: Optional[float] = None
        self.last_received_at: Optional[float] = None

        # Handler riêng cho từng loại message, đăng ký qua set_handler(MessageType.X, callback)
        self._handlers: dict[int, Callable[[MessageBase], None]] = {}
        # Handler chung, được gọi cho MỌI message nhận được (nếu có đăng ký)
        self._generic_handler: Optional[Callable[[MessageBase], None]] = None

        # Lưu các ACK đã nhận được, key = (robot_id, acked_type, task_id), value = thời điểm nhận.
        # Dùng cho wait_for_ack()/send_with_retry() bên dưới. Entry không ai tiêu thụ sau
        # ACK_TTL giây sẽ bị dọn (xem _prune_stale_acks_unlocked) để tránh phình vô hạn.
        self._received_acks: dict[tuple[int, int, int], float] = {}

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
                name="uart-listener-v2",
            )
            self.listen_thread.start()
            LOGGER.info("Đã khởi động luồng lắng nghe UART (binary v2).")

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
    def send_message(self, message: MessageBase) -> bool:
        """Đóng gói 1 object message (Heartbeat, TaskAssign, ...) thành nhị phân và gửi đi."""
        try:
            packet = bytes([BINARY_START_BYTE]) + message.encode()
        except struct.error as e:
            self.last_error = str(e)
            LOGGER.error(f"Dữ liệu vượt phạm vi kiểu khi encode {type(message).__name__}: {e}")
            return False

        with self._lock:
            conn = self.serial_conn
            if conn is None or not conn.is_open:
                LOGGER.error("Cổng UART chưa mở.")
                return False

            try:
                conn.write(packet)
                return True
            except Exception as e:
                self.last_error = str(e)
                LOGGER.error(f"Lỗi khi gửi message nhị phân: {e}")
                return False

    # ─────────────────────────────────────────────────────────────────────────
    def wait_for_ack(self, robot_id: int, acked_type: int, task_id: int, timeout: float = 1.0) -> bool:
        """Chờ tối đa `timeout` giây để nhận đúng 1 ACK khớp (robot_id, acked_type, task_id).
        Trả True nếu nhận được trong thời gian chờ, False nếu hết giờ."""
        key = (robot_id, int(acked_type), task_id)
        deadline = time.time() + timeout

        while time.time() < deadline:
            with self._lock:
                if key in self._received_acks:
                    del self._received_acks[key]  # tiêu thụ luôn, tránh dính vào lần chờ sau
                    return True
            time.sleep(0.02)

        return False

    # ─────────────────────────────────────────────────────────────────────────
    def send_with_retry(
        self,
        message: MessageBase,
        task_id: int,
        timeout: float = 1.0,
        max_retries: int = 3,
    ) -> bool:
        """Gửi 1 message quan trọng (TaskAssign, TaskCancel...), tự động gửi lại
        nếu không nhận được ACK trong `timeout` giây, tối đa `max_retries` lần.
        `robot_id` và `acked_type` được lấy trực tiếp từ `message` thay vì truyền tay,
        tránh trường hợp truyền lệch với message thực sự gửi đi.
        Trả True nếu cuối cùng có ACK, False nếu hết số lần retry mà vẫn không có."""
        robot_id = message.robot_id
        acked_type = message.MESSAGE_TYPE

        for attempt in range(1, max_retries + 1):
            if not self.send_message(message):
                LOGGER.error(f"Gửi thất bại (lỗi cổng UART) ở lần thử {attempt}.")
                return False

            if self.wait_for_ack(robot_id, acked_type, task_id, timeout=timeout):
                LOGGER.info(f"Nhận ACK cho task_id={task_id} sau {attempt} lần gửi.")
                return True

            LOGGER.warning(f"Không nhận ACK cho task_id={task_id}, lần thử {attempt}/{max_retries}.")

        LOGGER.error(f"Hết {max_retries} lần retry, task_id={task_id} không được xác nhận.")
        return False

    # ─────────────────────────────────────────────────────────────────────────
    def receive_message(self) -> Optional[MessageBase]:
        """Đọc và tự động phân tích 1 gói nhị phân từ UART, đồng thời cập nhật state
        + gọi handler tương ứng (giống receive_data() ở bản v1)."""
        message = self._read_one_message()
        if message is None:
            return None

        self._handle_received_message(message)
        return message

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
            }

    # ─────────────────────────────────────────────────────────────────────────
    def set_handler(self, message_type: int, handler: Optional[Callable[[MessageBase], None]]) -> None:
        """Đăng ký callback riêng cho 1 loại message cụ thể.
        Ví dụ: uart.set_handler(MessageType.TASK_STATUS, on_task_status)"""
        with self._lock:
            if handler is None:
                self._handlers.pop(message_type, None)
            else:
                self._handlers[message_type] = handler

    # ─────────────────────────────────────────────────────────────────────────
    def set_generic_handler(self, handler: Optional[Callable[[MessageBase], None]]) -> None:
        """Đăng ký callback được gọi cho MỌI message nhận được, bất kể loại gì
        (hữu ích cho việc log/monitor chung)."""
        with self._lock:
            self._generic_handler = handler

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

            self.receive_message()

            time.sleep(0.01)

    # ─────────────────────────────────────────────────────────────────────────
    def _read_one_message(self) -> Optional[MessageBase]:
        """Đọc đúng 1 gói nhị phân hoàn chỉnh từ UART (blocking theo số byte cần thiết,
        không dùng readline). Trả None nếu chưa có gói, sai start byte, message_type
        không rõ, đọc thiếu byte, hoặc CRC sai."""
        with self._lock:
            conn = self.serial_conn
            if conn is None or not conn.is_open:
                return None

            try:
                if conn.in_waiting <= 0:
                    return None

                start = conn.read(1)
                if not start or start[0] != BINARY_START_BYTE:
                    LOGGER.warning(f"Byte đầu không khớp start byte nhị phân: {start!r}")
                    return None

                type_byte = conn.read(1)
                if not type_byte:
                    return None
                message_type = type_byte[0]

                msg_class = MessageBase._registry.get(message_type)
                if msg_class is None:
                    LOGGER.warning(f"Không rõ message_type nhị phân: {message_type}")
                    return None

                payload_size = struct.calcsize(msg_class.FORMAT)
                remaining = payload_size - 1 + CRC_SIZE  # -1 vì message_type đã đọc ở trên
                rest = conn.read(remaining)
                if len(rest) != remaining:
                    LOGGER.warning("Đọc thiếu byte, gói nhị phân không đầy đủ.")
                    return None

                packet = type_byte + rest
            except Exception as e:
                self.last_error = str(e)
                LOGGER.error(f"Lỗi khi đọc message nhị phân: {e}")
                return None

        message = MessageBase.decode_any(packet)
        if message is None:
            LOGGER.warning("CRC sai, bỏ qua gói nhị phân.")
        return message

    # ─────────────────────────────────────────────────────────────────────────
    def _handle_received_message(self, message: MessageBase) -> None:
        with self._lock:
            now = time.time()
            self.last_received_at = now
            self.latest_received_message = message

            # Nếu đây là 1 gói ACK, ghi nhận lại để wait_for_ack()/send_with_retry() dùng.
            # Dùng duck-typing qua MESSAGE_TYPE thay vì import class Ack cụ thể,
            # giữ đúng nguyên tắc: uart_manager_v2 không cần biết chi tiết từng loại message con.
            if int(message.MESSAGE_TYPE) == int(MessageType.ACK):
                key = (message.robot_id, int(message.acked_type), message.task_id)
                self._received_acks[key] = now
                self._prune_stale_acks_unlocked(now)

            specific_handler = self._handlers.get(int(message.MESSAGE_TYPE))
            generic_handler = self._generic_handler

        if specific_handler is not None:
            try:
                specific_handler(message)
            except Exception as e:
                self.last_error = str(e)
                LOGGER.error(f"Lỗi khi xử lý handler cho {type(message).__name__}: {e}")

        if generic_handler is not None:
            try:
                generic_handler(message)
            except Exception as e:
                self.last_error = str(e)
                LOGGER.error(f"Lỗi khi xử lý generic handler: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    def _prune_stale_acks_unlocked(self, now: float) -> None:
        """Dọn các ACK đã lưu quá ACK_TTL giây mà không ai wait_for_ack() tới lấy.
        Phải gọi trong lúc đang giữ self._lock."""
        stale_keys = [key for key, received_at in self._received_acks.items() if now - received_at > ACK_TTL]
        for key in stale_keys:
            del self._received_acks[key]

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
def create_uart_manager_v2_from_config(*, connect: bool = False) -> UartManagerV2:
    uart_cfg = _load_uart_config()
    manager = UartManagerV2(
        port=uart_cfg.get("port", DEFAULT_PORT),
        baudrate=uart_cfg.get("baudrate", DEFAULT_BAUDRATE),
        timeout=DEFAULT_TIMEOUT,
    )

    if connect:
        manager.connect()

    return manager


# ─────────────────────────────────────────────────────────────────────────────
uart_manager_v2 = create_uart_manager_v2_from_config(connect=False)