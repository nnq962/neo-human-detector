# Message Spec - Robot Dispatch V2

Tài liệu này mô tả giao thức nhị phân đang được định nghĩa trong
`src/robot_dispatch_v2/datatypes.py`.

## Gửi task test qua API

FastAPI sở hữu kết nối `uart_manager_v2`. Khi vision Runtime đã dừng,
có thể gửi trực tiếp `TaskAssign` hoặc `TaskCancel` qua:

```text
POST /api/uart/messages
```

Service chờ ACK theo `ack_timeout_seconds`/`max_retries`, theo dõi task trong
memory và ACK các `TaskStatus` tương ứng. API trả `409 Conflict` nếu
Runtime đang chạy, nếu còn manual task active khi khởi động Runtime,
hoặc khi đổi cấu hình UART trong lúc UART đang được sử dụng.

Mục tiêu của V2 là bỏ format string/JSON khi gửi qua LoRa/UART, thay bằng các
packet nhị phân nhỏ, có kích thước cố định theo từng loại message.

---

## 1. Format Chung Của MessageBase

Tất cả message đều kế thừa `MessageBase` và tuân theo cùng một format gói tin:

```text
packet = payload + checksum
```

Trong đó:

| Thành phần | Kích thước | Mô tả |
|---|---:|---|
| `payload` | Tùy từng message | Dữ liệu nhị phân được đóng gói bằng `struct.pack(...)` |
| `checksum` | 2 byte | `uint16`, little-endian |

`checksum` không nằm trong payload. Khi nhận packet, code tách 2 byte cuối làm
checksum, phần còn lại là payload.

---

## 2. Quy Ước Payload

Mọi payload đều bắt đầu bằng field `message_type` 1 byte:

| Offset | Size | Field | Type | Mô tả |
|---:|---:|---|---|---|
| 0 | 1 | `message_type` | `uint8` | Định danh loại message |
| ... | ... | Payload riêng | ... | Các field còn lại tùy từng message |

Bên nhận chỉ cần đọc byte đầu tiên của payload để biết message thuộc loại nào.
`MessageBase.decode_any(packet)` dùng byte này để tra registry và gọi đúng class
decode tương ứng.

Tất cả số nhiều byte đều dùng little-endian theo `struct` format của Python.

---

## 3. Checksum

Trong code hiện tại, `encode()` tạo checksum như sau:

```python
crc = binascii.crc32(payload) & 0xFFFF
packet = payload + struct.pack("<H", crc)
```

Vì vậy, dù docstring gọi là CRC16, công thức thực tế là:

```text
checksum = crc32(payload) & 0xFFFF
```

Lưu ý triển khai firmware:

| Quy tắc | Mô tả |
|---|---|
| Vùng tính checksum | Chỉ tính trên `payload`, không tính 2 byte checksum cuối |
| Kiểu lưu checksum | `uint16`, little-endian |
| Khi checksum sai | Bỏ packet, coi như chưa nhận được |

---

## 4. Bảng MessageType

| Giá trị | Tên trong code | Hướng gửi | Ý nghĩa |
|---:|---|---|---|
| 0 | `HEARTBEAT` | Robot -> Dispatcher | Robot báo cáo vị trí và trạng thái định kỳ |
| 1 | `TASK_ASSIGN` | Dispatcher -> Robot | Dispatcher giao 1 task phục vụ |
| 2 | `TASK_STATUS` | Robot -> Dispatcher | Robot báo cáo tiến độ task |
| 3 | `TASK_CANCEL` | Dispatcher -> Robot | Dispatcher hủy 1 task đã giao |
| 4 | `ACK` | Hai chiều, tùy ngữ cảnh | Xác nhận đã nhận message quan trọng |

---

## 5. Bảng Mã Dùng Chung

### 5.1. RobotStateCode

Dùng trong `Heartbeat.state_code`.

| Giá trị | Tên trong code | Ý nghĩa |
|---:|---|---|
| 0 | `IDLE` | Robot đang rảnh, chờ lệnh |
| 1 | `SERVING` | Robot đang thực hiện task |
| 2 | `ERROR` | Robot đang gặp lỗi |

### 5.2. TaskStatusCode

Dùng trong `TaskStatus.status_code`.

| Giá trị | Tên trong code | Ý nghĩa |
|---:|---|---|
| 0 | `IN_PROGRESS` | Task đang được thực hiện |
| 1 | `COMPLETED` | Task đã hoàn thành |
| 2 | `FAILED` | Task thực hiện thất bại |

---

## 6. Quy Ước Đơn Vị

### 6.1. Tọa Độ X/Y

Trong Python, `x` và `y` dùng đơn vị mét dạng `float`. Khi đóng gói nhị phân,
code đổi sang centimet và lưu bằng `int16`:

```text
x_raw = round(x_met * 100)
y_raw = round(y_met * 100)
```

Khi parse ngược:

```text
x_met = x_raw / 100
y_met = y_raw / 100
```

Khoảng biểu diễn thực tế của `int16` theo đơn vị mét:

```text
-327.68 m đến +327.67 m
```

### 6.2. Góc Theta

Trong Python, `theta` dùng đơn vị radian dạng `float`. Khi đóng gói nhị phân,
code đổi sang milliradian và lưu bằng `int16`:

```text
theta_raw = round(theta_rad * 1000)
```

Khi parse ngược:

```text
theta_rad = theta_raw / 1000
```

Khoảng biểu diễn thực tế:

```text
-32.768 rad đến +32.767 rad
```

---

## 7. Chi Tiết Từng Loại Message

### 7.1. Ack

`Ack` xác nhận đã nhận thành công 1 message quan trọng. Class này dùng chung cho
`TaskAssign`, `TaskCancel`, và `TaskStatus`; không tách ACK riêng cho từng loại
message.

Format trong code:

```python
FORMAT = "<BBBB"
```

Payload:

| Offset | Size | Field | Type | Mô tả |
|---:|---:|---|---|---|
| 0 | 1 | `message_type` | `uint8` | Cố định = `MessageType.ACK` = 4 |
| 1 | 1 | `robot_id` | `uint8` | Robot liên quan tới ACK này |
| 2 | 1 | `acked_type` | `uint8` | Loại message được ACK, ví dụ `TASK_ASSIGN`/`TASK_CANCEL`/`TASK_STATUS` |
| 3 | 1 | `task_id` | `uint8` | Task cụ thể được ACK |

Kích thước packet:

| Thành phần | Byte |
|---|---:|
| Payload | 4 |
| Checksum | 2 |
| Tổng packet | 6 |

Ví dụ: ACK cho `TaskAssign` của `task_id=10` từ robot `1` thì
`acked_type = MessageType.TASK_ASSIGN = 1`.

---

### 7.2. Heartbeat

`Heartbeat` là message robot gửi định kỳ về Dispatcher để báo cáo vị trí và
trạng thái hiện tại.

Format trong code:

```python
FORMAT = "<BBIhhhB"
```

Payload:

| Offset | Size | Field | Type | Mô tả |
|---:|---:|---|---|---|
| 0 | 1 | `message_type` | `uint8` | Cố định = `MessageType.HEARTBEAT` = 0 |
| 1 | 1 | `robot_id` | `uint8` | ID robot |
| 2 | 4 | `timestamp` | `uint32` | Unix timestamp, đơn vị giây |
| 6 | 2 | `x` | `int16` | Vị trí x, mét -> centimet |
| 8 | 2 | `y` | `int16` | Vị trí y, mét -> centimet |
| 10 | 2 | `theta` | `int16` | Góc hướng, radian -> milliradian |
| 12 | 1 | `state_code` | `uint8` | Xem `RobotStateCode` |

Kích thước packet:

| Thành phần | Byte |
|---|---:|
| Payload | 13 |
| Checksum | 2 |
| Tổng packet | 15 |

---

### 7.3. TaskAssign

`TaskAssign` là message Dispatcher gửi để giao đúng 1 điểm phục vụ cho robot.
Mỗi packet chỉ chứa 1 task. Nếu cần giao nhiều điểm, gửi nhiều packet
`TaskAssign` liên tiếp với các `task_id` khác nhau.

Format trong code:

```python
FORMAT = "<BBBhhh"
```

Payload:

| Offset | Size | Field | Type | Mô tả |
|---:|---:|---|---|---|
| 0 | 1 | `message_type` | `uint8` | Cố định = `MessageType.TASK_ASSIGN` = 1 |
| 1 | 1 | `robot_id` | `uint8` | Robot nhận task |
| 2 | 1 | `task_id` | `uint8` | ID task, 0-255 |
| 3 | 2 | `x` | `int16` | Vị trí x, mét -> centimet |
| 5 | 2 | `y` | `int16` | Vị trí y, mét -> centimet |
| 7 | 2 | `theta` | `int16` | Góc đích, radian -> milliradian |

Kích thước packet:

| Thành phần | Byte |
|---|---:|
| Payload | 9 |
| Checksum | 2 |
| Tổng packet | 11 |

Ví dụ:

```python
TaskAssign(robot_id=1, task_id=10, x=1.23, y=4.56, theta=1.57)
```

Giá trị raw trước checksum:

| Field | Giá trị logic | Giá trị raw |
|---|---:|---:|
| `message_type` | `TASK_ASSIGN` | 1 |
| `robot_id` | 1 | 1 |
| `task_id` | 10 | 10 |
| `x` | 1.23 m | 123 |
| `y` | 4.56 m | 456 |
| `theta` | 1.57 rad | 1570 |

---

### 7.4. TaskStatus

`TaskStatus` là message robot gửi về Dispatcher để báo cáo trạng thái của 1 task
cụ thể.

Format trong code:

```python
FORMAT = "<BBBB"
```

Payload:

| Offset | Size | Field | Type | Mô tả |
|---:|---:|---|---|---|
| 0 | 1 | `message_type` | `uint8` | Cố định = `MessageType.TASK_STATUS` = 2 |
| 1 | 1 | `robot_id` | `uint8` | Robot đang báo cáo |
| 2 | 1 | `task_id` | `uint8` | Task được báo cáo |
| 3 | 1 | `status_code` | `uint8` | Xem `TaskStatusCode` |

Kích thước packet:

| Thành phần | Byte |
|---|---:|
| Payload | 4 |
| Checksum | 2 |
| Tổng packet | 6 |

#### Quy tắc gửi TaskStatus

Với mỗi `(robot_id, task_id)`, robot chỉ được có tối đa một `TaskStatus` đang
chờ ACK tại một thời điểm:

```text
Gửi TaskStatus
→ chờ ACK có acked_type=TASK_STATUS
→ nhận ACK thì mới gửi status tiếp theo
→ hết timeout thì gửi lại đúng TaskStatus cũ
```

Quy tắc stop-and-wait này là bắt buộc vì ACK hiện chỉ chứa `robot_id`,
`acked_type` và `task_id`; chưa có `sequence_id` để phân biệt ACK của
`IN_PROGRESS`, `COMPLETED` hoặc `FAILED` cho cùng một task.

---

### 7.5. TaskCancel

`TaskCancel` là message Dispatcher gửi để hủy 1 task cụ thể đang giao cho robot.
Thiết kế hiện tại chỉ gửi `robot_id` và `task_id`; không gửi `reason_code`.

Format trong code:

```python
FORMAT = "<BBB"
```

Payload:

| Offset | Size | Field | Type | Mô tả |
|---:|---:|---|---|---|
| 0 | 1 | `message_type` | `uint8` | Cố định = `MessageType.TASK_CANCEL` = 3 |
| 1 | 1 | `robot_id` | `uint8` | Robot đang giữ task |
| 2 | 1 | `task_id` | `uint8` | Task cần hủy |

Kích thước packet:

| Thành phần | Byte |
|---|---:|
| Payload | 3 |
| Checksum | 2 |
| Tổng packet | 5 |

Ví dụ:

```python
TaskCancel(robot_id=1, task_id=10)
```

Giá trị raw trước checksum:

| Field | Giá trị raw |
|---|---:|
| `message_type` | 3 |
| `robot_id` | 1 |
| `task_id` | 10 |

---

## 8. Lưu Ý Triển Khai Firmware

- Không parse theo string, không parse JSON.
- Byte đầu tiên của payload luôn là `message_type`.
- Mỗi packet kết thúc bằng 2 byte checksum little-endian.
- Checksum tính trên payload, không tính trên 2 byte checksum cuối.
- Công thức checksum hiện tại là `crc32(payload) & 0xFFFF`, không phải biến thể
  CRC-16/CCITT truyền thống.
- `task_id` hiện tại là `uint8`, tối đa 255. Nếu cần chạy lâu với nhiều task hơn,
  cần đổi `TaskAssign`, `TaskStatus`, `TaskCancel`, và `Ack` sang `uint16`.
- `Ack.acked_type` nên dùng đúng giá trị trong `MessageType`.
- `TaskStatus` phải tuân theo stop-and-wait: chờ ACK trước khi gửi status tiếp
  theo cho cùng task.
