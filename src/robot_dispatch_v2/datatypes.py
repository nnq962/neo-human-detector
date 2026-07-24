"""
Giao thức nhị phân cho robot giao tiếp qua LoRa.
"""

import struct
import binascii
from dataclasses import dataclass
from enum import IntEnum

from utils import LOGGER


# ─────────────────────────────────────────────────────────────────────────────
class MessageType(IntEnum):
    """
    Các loại message được sử dụng trong giao tiếp giữa Dispatcher và Robot.

    Members:
        HEARTBEAT: Robot gửi định kỳ để báo cáo vị trí và trạng thái.
        TASK_ASSIGN: Dispatcher giao một task cho robot.
        TASK_STATUS: Robot báo cáo tiến độ thực hiện task.
        TASK_CANCEL: Dispatcher hủy task đang giao cho robot.
        ACK: Xác nhận message.
        MOVE_TO_POINT: Dispatcher yêu cầu robot di chuyển tới một pose đích.
    """
    HEARTBEAT     = 0
    TASK_ASSIGN   = 1
    TASK_STATUS   = 2
    TASK_CANCEL   = 3
    ACK            = 4
    MOVE_TO_POINT = 5


# ─────────────────────────────────────────────────────────────────────────────
class RobotStateCode(IntEnum):
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
class TaskStatusCode(IntEnum):
    """
    Danh sách các trạng thái task.

    Members:
        IN_PROGRESS: Task đang được thực hiện.
        COMPLETED: Task đã hoàn thành.
        FAILED: Task thực hiện thất bại.
    """
    IN_PROGRESS = 0
    COMPLETED   = 1
    FAILED      = 2


# ─────────────────────────────────────────────────────────────────────────────
class AckResultCode(IntEnum):
    """
    Kết quả tiếp nhận message được robot hoặc Dispatcher trả về trong ACK.

    Members:
        ACCEPTED: Bên nhận đã tiếp nhận và chấp nhận xử lý message.
        REJECTED: Bên nhận đã đọc được message nhưng từ chối xử lý.
    """

    ACCEPTED = 0
    REJECTED = 1


# ─────────────────────────────────────────────────────────────────────────────
class AckReasonCode(IntEnum):
    """
    Nguyên nhân chi tiết đi kèm kết quả ACK.

    Members:
        NONE: Không có lỗi; thường dùng khi message được chấp nhận.
        ROBOT_BUSY: Robot đang bận nên không thể nhận thêm lệnh.
        ROBOT_ERROR: Robot đang ở trạng thái lỗi.
        INVALID_COMMAND: Nội dung lệnh không hợp lệ hoặc không được hỗ trợ.
        OUT_OF_RANGE: Pose hoặc tham số của lệnh nằm ngoài phạm vi cho phép.
        DUPLICATE_REFERENCE: Reference ID đã được dùng cho một message khác.
    """

    NONE                = 0
    ROBOT_BUSY          = 1
    ROBOT_ERROR         = 2
    INVALID_COMMAND     = 3
    OUT_OF_RANGE        = 4
    DUPLICATE_REFERENCE = 5


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
        """Đóng gói các field message thành payload chưa có checksum."""
        raise NotImplementedError

    @classmethod
    def from_payload(cls, payload: bytes):
        """Khôi phục message từ payload đã được kiểm tra checksum."""
        raise NotImplementedError

    def encode(self) -> bytes:
        """Đóng gói payload + checksum (crc32(payload) & 0xFFFF), trả về bytes sẵn sàng gửi qua LoRa."""
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
            LOGGER.warning(f"Không rõ message_type={message_type}, bỏ qua gói tin")
            return None
        return msg_class.decode(packet)


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Ack(MessageBase):
    """
    Phản hồi kết quả tiếp nhận một message quan trọng.

    `reference_id` mang `task_id` khi ACK message liên quan tới task, hoặc mang
    `move_id` khi ACK MoveToPoint. Kết hợp `(robot_id, acked_type, reference_id)`
    định danh duy nhất message đang được phản hồi.

    Cấu trúc payload (chưa gồm CRC), little-endian:
        message_type : uint8  (1 byte) - cố định = MessageType.ACK
        robot_id     : uint8  (1 byte) - robot liên quan tới ACK
        acked_type   : uint8  (1 byte) - loại message đang được ACK
        reference_id: uint8  (1 byte) - task_id hoặc move_id được tham chiếu
        result_code  : uint8  (1 byte) - xem AckResultCode
        reason_code  : uint8  (1 byte) - xem AckReasonCode

    Tổng payload = 6 byte, + 2 byte checksum = 8 byte/gói.

    """

    MESSAGE_TYPE = MessageType.ACK
    FORMAT = '<BBBBBB'

    robot_id: int
    acked_type: int
    reference_id: int
    result_code: int = AckResultCode.ACCEPTED
    reason_code: int = AckReasonCode.NONE

    def to_payload(self) -> bytes:
        """Đóng gói ACK thành payload nhị phân."""
        return struct.pack(
            self.FORMAT,
            self.MESSAGE_TYPE,
            self.robot_id,
            self.acked_type,
            self.reference_id,
            self.result_code,
            self.reason_code,
        )

    @classmethod
    def from_payload(cls, payload: bytes):
        """Giải mã payload ACK thành object."""
        (
            _,
            robot_id,
            acked_type,
            reference_id,
            result_code,
            reason_code,
        ) = struct.unpack(cls.FORMAT, payload)
        return cls(robot_id, acked_type, reference_id, result_code, reason_code)


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
        state_code   : uint8   (1 byte)  - mã trạng thái robot

    Tổng payload = 13 byte, + 2 byte checksum = 15 byte/gói.
    """

    MESSAGE_TYPE = MessageType.HEARTBEAT
    FORMAT = '<BBIhhhB'  # B=uint8, I=uint32, h=int16 (xem struct docs để tra ký hiệu khác)

    robot_id: int
    timestamp: int
    x: float       # mét (float, để code Python dùng tự nhiên)
    y: float       # mét
    theta: float   # radian
    state_code: int

    def to_payload(self) -> bytes:
        """Đóng gói Heartbeat, quy đổi tọa độ và góc sang số nguyên."""
        return struct.pack(
            self.FORMAT,
            self.MESSAGE_TYPE,
            self.robot_id,
            self.timestamp,
            round(self.x * 100),      # mét -> cm
            round(self.y * 100),      # mét -> cm
            round(self.theta * 1000), # radian -> milliradian
            self.state_code,
        )

    @classmethod
    def from_payload(cls, payload: bytes):
        """Giải mã Heartbeat và khôi phục đơn vị mét/radian."""
        _, robot_id, timestamp, x_raw, y_raw, theta_raw, state_code = struct.unpack(cls.FORMAT, payload)
        return cls(
            robot_id=robot_id,
            timestamp=timestamp,
            x=x_raw / 100,
            y=y_raw / 100,
            theta=theta_raw / 1000,
            state_code=state_code,
        )


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TaskAssign(MessageBase):
    """
    Dispatcher giao 1 task (1 điểm phục vụ) cho robot.

    Cấu trúc payload (chưa gồm CRC), little-endian:
        message_type : uint8  (1 byte)  - cố định = MessageType.TASK_ASSIGN
        robot_id     : uint8  (1 byte)
        task_id      : uint8  (1 byte)  - định danh riêng của task này
        x            : int16  (2 byte)  - mét -> cm (x*100)
        y            : int16  (2 byte)  - mét -> cm (y*100)
        theta        : int16  (2 byte)  - radian -> milliradian (theta*1000)

    Tổng payload = 9 byte, + 2 byte checksum = 11 byte/gói.

    Nguyên tắc: mỗi gói chỉ chứa ĐÚNG 1 điểm phục vụ. Cần nhiều điểm cho cùng
    1 robot -> gửi nhiều gói TaskAssign liên tiếp, mỗi gói 1 task_id riêng.
    """

    MESSAGE_TYPE = MessageType.TASK_ASSIGN
    FORMAT = '<BBBhhh'

    robot_id: int
    task_id: int
    x: float      # mét
    y: float      # mét
    theta: float  # radian

    def to_payload(self) -> bytes:
        """Đóng gói TaskAssign, quy đổi pose đích sang số nguyên."""
        return struct.pack(
            self.FORMAT, self.MESSAGE_TYPE, self.robot_id, self.task_id,
            round(self.x * 100), round(self.y * 100), round(self.theta * 1000),
        )

    @classmethod
    def from_payload(cls, payload: bytes):
        """Giải mã TaskAssign và khôi phục pose đích."""
        _, robot_id, task_id, x_raw, y_raw, theta_raw = struct.unpack(cls.FORMAT, payload)
        return cls(robot_id, task_id, x_raw / 100, y_raw / 100, theta_raw / 1000)


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class MoveToPoint(MessageBase):
    """
    Dispatcher yêu cầu robot di chuyển tới một pose đích.

    Cấu trúc payload (chưa gồm CRC), little-endian:
        message_type : uint8  (1 byte) - cố định = MessageType.MOVE_TO_POINT
        robot_id     : uint8  (1 byte) - robot nhận lệnh di chuyển
        move_id      : uint8  (1 byte) - định danh riêng của lệnh di chuyển
        x            : int16  (2 byte) - mét -> cm (x*100)
        y            : int16  (2 byte) - mét -> cm (y*100)
        theta        : int16  (2 byte) - radian -> milliradian (theta*1000)

    Tổng payload = 9 byte, + 2 byte checksum = 11 byte/gói.
    Robot phản hồi bằng Ack có acked_type=MOVE_TO_POINT và
    reference_id=move_id.
    """

    MESSAGE_TYPE = MessageType.MOVE_TO_POINT
    FORMAT = '<BBBhhh'

    robot_id: int
    move_id: int
    x: float
    y: float
    theta: float

    def to_payload(self) -> bytes:
        """Đóng gói MoveToPoint, quy đổi pose đích sang số nguyên."""
        return struct.pack(
            self.FORMAT,
            self.MESSAGE_TYPE,
            self.robot_id,
            self.move_id,
            round(self.x * 100),
            round(self.y * 100),
            round(self.theta * 1000),
        )

    @classmethod
    def from_payload(cls, payload: bytes):
        """Giải mã MoveToPoint và khôi phục pose đích."""
        _, robot_id, move_id, x_raw, y_raw, theta_raw = struct.unpack(
            cls.FORMAT,
            payload,
        )
        return cls(
            robot_id,
            move_id,
            x_raw / 100,
            y_raw / 100,
            theta_raw / 1000,
        )


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TaskStatus(MessageBase):
    """
    Robot báo cáo tiến độ 1 task cụ thể về dispatcher.

    Cấu trúc payload:
        message_type : uint8 (1 byte) - cố định = MessageType.TASK_STATUS
        robot_id     : uint8 (1 byte)
        task_id      : uint8 (1 byte) - khớp với task_id trong TaskAssign tương ứng
        status_code  : uint8 (1 byte) - 0=đang làm, 1=hoàn thành, 2=thất bại

    Tổng payload = 4 byte, + 2 byte checksum = 6 byte/gói.

    Robot phải chờ ACK của mỗi TaskStatus trước khi gửi status tiếp theo cho
    cùng task. ACK hiện không có sequence_id nên chỉ hỗ trợ stop-and-wait.
    """

    MESSAGE_TYPE = MessageType.TASK_STATUS
    FORMAT = '<BBBB'

    robot_id: int
    task_id: int
    status_code: int

    def to_payload(self) -> bytes:
        """Đóng gói trạng thái task thành payload nhị phân."""
        return struct.pack(self.FORMAT, self.MESSAGE_TYPE, self.robot_id, self.task_id, self.status_code)

    @classmethod
    def from_payload(cls, payload: bytes):
        """Giải mã payload trạng thái task thành object."""
        _, robot_id, task_id, status_code = struct.unpack(cls.FORMAT, payload)
        return cls(robot_id, task_id, status_code)


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TaskCancel(MessageBase):
    """
    Dispatcher hủy 1 task cụ thể đang giao cho robot.

    Cấu trúc payload:
        message_type : uint8 (1 byte) - cố định = MessageType.TASK_CANCEL
        robot_id     : uint8 (1 byte)
        task_id      : uint8 (1 byte) - task cần hủy, khớp task_id trong TaskAssign

    Tổng payload = 3 byte, + 2 byte checksum = 5 byte/gói.
    """

    MESSAGE_TYPE = MessageType.TASK_CANCEL
    FORMAT = '<BBB'

    robot_id: int
    task_id: int

    def to_payload(self) -> bytes:
        """Đóng gói yêu cầu hủy task thành payload nhị phân."""
        return struct.pack(self.FORMAT, self.MESSAGE_TYPE, self.robot_id, self.task_id)

    @classmethod
    def from_payload(cls, payload: bytes):
        """Giải mã payload hủy task thành object."""
        _, robot_id, task_id = struct.unpack(cls.FORMAT, payload)
        return cls(robot_id, task_id)
