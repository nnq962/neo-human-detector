"""
Giao thức nhị phân cho robot giao tiếp qua LoRa.
"""

import struct
import binascii
import time
from dataclasses import dataclass
from enum import IntEnum


# ─────────────────────────────────────────────────────────────────────────────
class MessageType(IntEnum):
    """
    Các loại message được sử dụng trong giao tiếp giữa Dispatcher và Robot.

    Members:
        HEARTBEAT: Robot gửi định kỳ để báo cáo vị trí và trạng thái.
        TASK_ASSIGN: Dispatcher giao một task cho robot.
        TASK_STATUS: Robot báo cáo tiến độ thực hiện task.
        TASK_CANCEL: Dispatcher hủy task đang giao cho robot.
    """
    HEARTBEAT   = 0
    TASK_ASSIGN = 1
    TASK_STATUS = 2
    TASK_CANCEL = 3

# ─────────────────────────────────────────────────────────────────────────────
class RobotState(IntEnum):
    """
    Danh sách các trạng thái robot.

    Members:
        IDLE: Robot đang rảnh, chờ lệnh.
        SERVING: Robot đang thực hiện task.
        ERROR: Robot đang gặp lỗi.
    """
    IDLE    = 0
    SERVING = 1
    ERROR   = 2


# ─────────────────────────────────────────────────────────────────────────────
class MessageBase:
    """
    Base class cho mọi loại message gửi/nhận qua LoRa.
    Mọi loại message (Heartbeat, TaskAssign, TaskStatus, ...) đều kế thừa class này.

    Mỗi subclass phải khai báo:
    - MESSAGE_TYPE: số nguyên duy nhất định danh loại message (0, 1, 2, ...)
    - FORMAT: struct format string (xem thêm tại https://docs.python.org/3/library/struct.html)
    - to_payload(self) -> bytes: đóng gói field thành bytes (không gồm CRC)
    - from_payload(cls, payload: bytes) -> instance: parse bytes ngược lại thành object
    """

    MESSAGE_TYPE: int = None
    FORMAT: str = None

    # Registry dùng CHUNG cho toàn bộ subclass, key = MESSAGE_TYPE, value = class
    _registry = {}

    def __init_subclass__(cls, **kwargs):
        """
        Python tự động gọi hàm này ngay khi 1 class kế thừa MessageBase được định nghĩa
        (ngay lúc import, không cần tạo object). Ta lợi dụng để tự động đăng ký class
        vào registry, đồng thời báo lỗi ngay nếu 2 class lỡ trùng MESSAGE_TYPE.
        """
        super().__init_subclass__(**kwargs)

        if cls.MESSAGE_TYPE is None:
            raise ValueError(f"{cls.__name__} phải khai báo MESSAGE_TYPE")

        if cls.MESSAGE_TYPE in MessageBase._registry:
            existing = MessageBase._registry[cls.MESSAGE_TYPE].__name__
            raise ValueError(
                f"Trùng MESSAGE_TYPE={cls.MESSAGE_TYPE} giữa {cls.__name__} và {existing}"
            )

        MessageBase._registry[cls.MESSAGE_TYPE] = cls

    def to_payload(self) -> bytes:
        raise NotImplementedError

    @classmethod
    def from_payload(cls, payload: bytes):
        raise NotImplementedError

    def encode(self) -> bytes:
        """Đóng gói payload + CRC16, trả về bytes sẵn sàng gửi qua LoRa."""
        payload = self.to_payload()
        crc = binascii.crc32(payload) & 0xFFFF
        return payload + struct.pack('<H', crc)

    @classmethod
    def decode(cls, packet: bytes):
        """Tách CRC khỏi packet, kiểm tra, rồi parse thành object.
        Trả về None nếu CRC sai (nghĩa là data đã bị lỗi trên đường truyền)."""
        payload, received_crc = packet[:-2], struct.unpack('<H', packet[-2:])[0]
        calculated_crc = binascii.crc32(payload) & 0xFFFF
        if received_crc != calculated_crc:
            return None
        return cls.from_payload(payload)

    @staticmethod
    def decode_any(packet: bytes):
        """
        Hàm DUY NHẤT cần gọi ở nơi nhận dữ liệu, khi chưa biết trước gói tin là loại gì.
        Tự đọc byte đầu tiên (message_type), tra registry để biết dùng class nào decode.
        Gọi qua: MessageBase.decode_any(raw_bytes)
        """
        message_type = packet[0]
        msg_class = MessageBase._registry.get(message_type)
        if msg_class is None:
            print(f"[WARN] Không rõ message_type={message_type}, bỏ qua gói tin")
            return None
        return msg_class.decode(packet)


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Heartbeat(MessageBase):
    """
    Message định kỳ robot gửi về báo cáo vị trí + trạng thái.

    Cấu trúc payload (chưa gồm CRC), little-endian:
        message_type : uint8   (1 byte)  - cố định = 0
        robot_id     : uint8   (1 byte)  - id robot, số nguyên đơn giản (1, 2, 3...)
        timestamp    : uint32  (4 byte)  - unix timestamp (giây)
        x            : int16   (2 byte)  - vị trí x, đơn vị gốc = mét, lưu dạng cm (x*100)
        y            : int16   (2 byte)  - vị trí y, đơn vị gốc = mét, lưu dạng cm (y*100)
        theta        : int16   (2 byte)  - góc hướng, đơn vị gốc = radian, lưu dạng milliradian (theta*1000)
        state        : uint8   (1 byte)  - mã trạng thái robot

    Tổng payload = 13 byte, + 2 byte CRC16 = 15 byte/gói.
    """

    MESSAGE_TYPE = MessageType.HEARTBEAT
    FORMAT = '<BBIhhhB'  # B=uint8, I=uint32, h=int16 (xem struct docs để tra ký hiệu khác)

    robot_id: int
    timestamp: int
    x: float       # mét (float, để code Python dùng tự nhiên)
    y: float       # mét
    theta: float   # radian
    state: int

    def to_payload(self) -> bytes:
        return struct.pack(
            self.FORMAT,
            self.MESSAGE_TYPE,
            self.robot_id,
            self.timestamp,
            round(self.x * 100),      # mét -> cm
            round(self.y * 100),      # mét -> cm
            round(self.theta * 1000), # radian -> milliradian
            self.state,
        )

    @classmethod
    def from_payload(cls, payload: bytes):
        _, robot_id, timestamp, x_raw, y_raw, theta_raw, state = struct.unpack(cls.FORMAT, payload)
        return cls(
            robot_id=robot_id,
            timestamp=timestamp,
            x=x_raw / 100,
            y=y_raw / 100,
            theta=theta_raw / 1000,
            state=state,
        )


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TaskAssign(MessageBase):
    """
    Message Dispatcher gửi để giao một task phục vụ cho robot.

    Message này dùng khi Dispatcher đã chọn được robot phù hợp và cần robot đi
    tới vị trí phục vụ. Đây là lệnh quan trọng, phía Dispatcher nên chờ ACK từ
    robot và retry nếu quá timeout, vì mất message này đồng nghĩa robot không
    biết có task mới.

    Cấu trúc payload (chưa gồm CRC), little-endian:
        message_type : uint8   (1 byte)  - cố định = 1
        msg_id       : uint16  (2 byte)  - id message để khớp ACK/retry
        robot_id     : uint8   (1 byte)  - id robot nhận task
        task_id      : uint16  (2 byte)  - id task cần thực hiện
        x            : int16   (2 byte)  - vị trí x, đơn vị gốc = mét, lưu dạng cm (x*100)
        y            : int16   (2 byte)  - vị trí y, đơn vị gốc = mét, lưu dạng cm (y*100)

    Tổng payload = 10 byte, + 2 byte CRC16 = 12 byte/gói.
    """

    MESSAGE_TYPE = MessageType.TASK_ASSIGN
    FORMAT = '<BHBHhh'  # B=uint8, H=uint16, h=int16

    msg_id: int
    robot_id: int
    task_id: int
    x: float  # mét
    y: float  # mét

    def to_payload(self) -> bytes:
        return struct.pack(
            self.FORMAT,
            self.MESSAGE_TYPE,
            self.msg_id,
            self.robot_id,
            self.task_id,
            round(self.x * 100),  # mét -> cm
            round(self.y * 100),  # mét -> cm
        )

    @classmethod
    def from_payload(cls, payload: bytes):
        _, msg_id, robot_id, task_id, x_raw, y_raw = struct.unpack(cls.FORMAT, payload)
        return cls(
            msg_id=msg_id,
            robot_id=robot_id,
            task_id=task_id,
            x=x_raw / 100,
            y=y_raw / 100,
        )


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TaskCancel(MessageBase):
    """
    Message Dispatcher gửi để hủy một task đã giao cho robot.

    Message này dùng khi task không còn nên được thực hiện nữa, ví dụ zone đã
    trống trước khi robot tới, Dispatcher phát hiện giao trùng, hoặc có thao tác
    hủy thủ công. Đây cũng là lệnh quan trọng: nếu robot không nhận được lệnh
    hủy, nó có thể tiếp tục đi phục vụ một vị trí không còn cần phục vụ. Vì vậy
    phía Dispatcher nên chờ ACK từ robot và retry nếu quá timeout.

    Cấu trúc payload (chưa gồm CRC), little-endian:
        message_type : uint8   (1 byte)  - cố định = 3
        msg_id       : uint16  (2 byte)  - id message để khớp ACK/retry
        robot_id     : uint8   (1 byte)  - id robot đang giữ task
        task_id      : uint16  (2 byte)  - id task cần hủy
        reason_code  : uint8   (1 byte)  - lý do hủy task

    Bảng reason_code dự kiến:
        0: duplicate       - task bị trùng hoặc đã có robot khác xử lý
        1: seat_empty      - vị trí/zone đã trống trước khi robot phục vụ
        2: manual_override - người vận hành hủy thủ công

    Tổng payload = 7 byte, + 2 byte CRC16 = 9 byte/gói.
    """

    MESSAGE_TYPE = MessageType.TASK_CANCEL
    FORMAT = '<BHBHB'  # B=uint8, H=uint16

    msg_id: int
    robot_id: int
    task_id: int
    reason_code: int

    def to_payload(self) -> bytes:
        return struct.pack(
            self.FORMAT,
            self.MESSAGE_TYPE,
            self.msg_id,
            self.robot_id,
            self.task_id,
            self.reason_code,
        )

    @classmethod
    def from_payload(cls, payload: bytes):
        _, msg_id, robot_id, task_id, reason_code = struct.unpack(cls.FORMAT, payload)
        return cls(
            msg_id=msg_id,
            robot_id=robot_id,
            task_id=task_id,
            reason_code=reason_code,
        )
