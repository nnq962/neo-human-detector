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
frame nhị phân nhỏ, có kích thước cố định theo từng loại message.

---

## 1. Format MessageBase Và UART Wire Frame

Tất cả message đều kế thừa `MessageBase`. Hàm `MessageBase.encode()` tạo packet
nội bộ theo format:

```text
message_packet = payload + checksum
```

Khi packet được truyền qua UART, `UartManagerV2` thêm 2 byte đóng khung (framing)
ở phía trước: 1 byte đánh dấu bắt đầu, và 1 byte khai báo độ dài. Format đầy đủ
thực sự xuất hiện trên đường truyền là:

```text
uart_frame = start_byte + length + payload + checksum
           = 0xAA       + length + payload + checksum
```

| Thành phần | Kích thước | Mô tả |
|---|---:|---|
| `start_byte` | 1 byte | Cố định `0xAA`, đánh dấu bắt đầu một UART frame |
| `length` | 1 byte | `uint8`, số byte còn lại NGAY SAU chính field này (= `payload + checksum`) |
| `payload` | Tùy từng message | Dữ liệu nhị phân được đóng gói bằng `struct.pack(...)`, byte đầu luôn là `message_type` |
| `checksum` | 2 byte | `uint16`, little-endian |

Minh họa thứ tự byte:

```text
+----------+----------+-----------------------------+--------------------+
|   0xAA   |  length  |           payload           |      checksum      |
+----------+----------+-----------------------------+--------------------+
  1 byte      1 byte      kích thước tùy message       2 byte little-endian
                        └──────────── length byte đúng bằng phần này ─────┘
```

Phân biệt các khái niệm trong tài liệu:

| Thành phần | Kích thước | Mô tả |
|---|---:|---|
| MessageBase packet | `payload + 2` byte | Kết quả của `MessageBase.encode()`, chưa có `0xAA`/`length` |
| UART wire frame | `payload + 4` byte | Toàn bộ dữ liệu thực sự được ghi xuống UART |

**Vì sao có `length`:** trước đây bên nhận phải tra `message_type` vào bảng
`MessageBase._registry` để biết `FORMAT` của loại message đó, từ đó suy ra cần
đọc thêm bao nhiêu byte. Cách này buộc bất kỳ ai đọc UART (kể cả một bên chỉ
forward dữ liệu, không quan tâm nội dung) cũng phải biết toàn bộ bảng
`message_type -> FORMAT` nội bộ của Python. Thêm `length` giải quyết việc này:
**chỉ cần đọc 1 byte `length` là biết chính xác điểm kết thúc gói**, không cần
biết `message_type` là loại gì, không cần bảng tra cứu nào cả — áp dụng được
cho MỌI loại message, kể cả loại chưa từng được định nghĩa.

`UartManagerV2.send_message()` tự thêm `0xAA` + `length` khi Python gửi. Khi
nhận, `UartManagerV2._read_one_message()` đọc `0xAA`, đọc `length`, rồi đọc
đúng `length` byte tiếp theo (= `payload + checksum`) và chuyển cho
`MessageBase.decode_any()`.

Firmware/bên forward gửi message về Python phải tự thêm `0xAA` + `length`.
Nếu thiếu 1 trong 2 byte này, UART manager sẽ bỏ frame. `start_byte` và
`length` đều không thuộc `payload` và không được tính vào checksum.

---

## 2. Quy Ước Payload

Mọi payload đều bắt đầu bằng field `message_type` 1 byte:

| Offset | Size | Field | Type | Mô tả |
|---:|---:|---|---|---|
| 0 | 1 | `message_type` | `uint8` | Định danh loại message |
| ... | ... | Payload riêng | ... | Các field còn lại tùy từng message |

Bên nhận chỉ cần đọc byte đầu tiên của payload để biết message thuộc loại nào.
`MessageBase.decode_any(message_packet)` dùng byte này để tra registry và gọi
đúng class decode tương ứng. Byte `0xAA` và byte `length` đã được UART manager
đọc bỏ trước bước này (dùng `length` để biết cần đọc bao nhiêu byte, không cần
tra `message_type` trước), vì vậy offset 0 trong các bảng payload bên dưới
luôn là `message_type`.

Tất cả số nhiều byte đều dùng little-endian theo `struct` format của Python.

---

## 3. Checksum

Trong code hiện tại, `encode()` tạo checksum như sau:

```python
crc = binascii.crc32(payload) & 0xFFFF
message_packet = payload + struct.pack("<H", crc)
```

Vì vậy, dù docstring gọi là CRC16, công thức thực tế là:

```text
checksum = crc32(payload) & 0xFFFF
```

Lưu ý triển khai firmware:

| Quy tắc | Mô tả |
|---|---|
| Vùng tính checksum | Chỉ tính trên `payload` |
| Byte không tham gia checksum | Không tính `start_byte = 0xAA` và không tính 2 byte checksum cuối |
| Kiểu lưu checksum | `uint16`, little-endian |
| Khi checksum sai | Bỏ frame, coi như chưa nhận được |

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

Kích thước frame truyền qua UART:

| Thành phần | Byte |
|---|---:|
| Start byte `0xAA` | 1 |
| Length | 1 |
| Payload | 4 |
| Checksum | 2 |
| Tổng UART frame | 8 |

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

Kích thước frame truyền qua UART:

| Thành phần | Byte |
|---|---:|
| Start byte `0xAA` | 1 |
| Length | 1 |
| Payload | 13 |
| Checksum | 2 |
| Tổng UART frame | 17 |

---

### 7.3. TaskAssign

`TaskAssign` là message Dispatcher gửi để giao đúng 1 điểm phục vụ cho robot.
Mỗi frame chỉ chứa 1 task. Nếu cần giao nhiều điểm, gửi nhiều frame
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

Kích thước frame truyền qua UART:

| Thành phần | Byte |
|---|---:|
| Start byte `0xAA` | 1 |
| Length | 1 |
| Payload | 9 |
| Checksum | 2 |
| Tổng UART frame | 13 |

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

Kích thước frame truyền qua UART:

| Thành phần | Byte |
|---|---:|
| Start byte `0xAA` | 1 |
| Length | 1 |
| Payload | 4 |
| Checksum | 2 |
| Tổng UART frame | 8 |

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

Kích thước frame truyền qua UART:

| Thành phần | Byte |
|---|---:|
| Start byte `0xAA` | 1 |
| Length | 1 |
| Payload | 3 |
| Checksum | 2 |
| Tổng UART frame | 7 |

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
- Mỗi UART frame phải bắt đầu bằng byte cố định `0xAA`.
- Ngay sau `0xAA` là 1 byte `length` (`uint8`) = số byte còn lại của frame
  (payload + checksum). Đọc xong `length` byte đó là hết đúng 1 frame, không
  cần biết `message_type` là gì.
- Byte đầu tiên của payload (byte thứ 3 trong frame, sau `0xAA` và `length`)
  luôn là `message_type`.
- Mỗi frame kết thúc bằng 2 byte checksum little-endian.
- Checksum chỉ tính trên payload; không tính `0xAA`, không tính `length`, và
  không tính 2 byte checksum cuối.
- Khi Python gửi bằng `UartManagerV2.send_message()`, manager tự thêm `0xAA` +
  `length`. Firmware/bên forward gửi Heartbeat, TaskStatus hoặc ACK về Python
  phải tự thêm cả 2 byte này.
- `length` tối đa 255 (`uint8`). Toàn bộ message hiện tại (payload + checksum)
  đều dưới 20 byte nên còn rất nhiều dư địa.
- Công thức checksum hiện tại là `crc32(payload) & 0xFFFF`, không phải biến thể
  CRC-16/CCITT truyền thống.
- `task_id` hiện tại là `uint8`, tối đa 255. Nếu cần chạy lâu với nhiều task hơn,
  cần đổi `TaskAssign`, `TaskStatus`, `TaskCancel`, và `Ack` sang `uint16`.
- `Ack.acked_type` nên dùng đúng giá trị trong `MessageType`.
- `TaskStatus` phải tuân theo stop-and-wait: chờ ACK trước khi gửi status tiếp
  theo cho cùng task.
