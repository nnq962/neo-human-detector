# Message Spec - Robot Dispatch V2

Tài liệu này mô tả giao thức nhị phân đang được định nghĩa trong
`src/robot_dispatch_v2/datatypes.py`.

## Gửi lệnh thủ công qua API

FastAPI sở hữu kết nối `uart_manager_v2`. Khi vision Runtime đã dừng,
có thể gửi trực tiếp `TaskAssign`, `TaskCancel` hoặc `MoveToPoint` qua:

```text
POST /api/uart/messages
```

Riêng `MoveToPoint` có thêm endpoint thuận tiện:

```text
POST /api/uart/move-to-point
```

Body:

```json
{
  "robot_id": 1,
  "x": 1.5,
  "y": 2.0,
  "theta": 0.25
}
```

Backend cấp `move_id` tuần tự theo từng robot trong khoảng 0-255; client không
được tự truyền ID này. API chỉ trả thành công khi robot phản hồi ACK `ACCEPTED`
và trả `move_id` đã cấp trong response.

Service chờ ACK theo `ack_timeout_seconds`/`max_retries`. `TaskAssign` được
theo dõi trong memory để xử lý `TaskStatus`; `MoveToPoint` có registry riêng để
không cấp hai lệnh đồng thời cho cùng robot. Một ID được giữ trong suốt các lần
retry và chỉ được giải phóng sau khi backend quan sát robot đã chạy rồi trở về
`IDLE`. API trả `409 Conflict` nếu Runtime đang chạy, robot đang bận, còn manual
task active khi khởi động Runtime, hoặc khi đổi cấu hình UART trong lúc UART
đang được sử dụng.

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
| 4 | `ACK` | Hai chiều, tùy ngữ cảnh | Phản hồi chấp nhận hoặc từ chối message |
| 5 | `MOVE_TO_POINT` | Dispatcher -> Robot | Yêu cầu robot di chuyển tới một pose đích |

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

### 5.3. AckResultCode

Dùng trong `Ack.result_code` để cho biết bên nhận chấp nhận hay từ chối xử lý
message. ACK có nghĩa là message đã được đọc và phân tích; `result_code` mới là
kết quả tiếp nhận ở tầng nghiệp vụ.

| Giá trị | Tên trong code | Ý nghĩa |
|---:|---|---|
| 0 | `ACCEPTED` | Message đã được tiếp nhận và chấp nhận xử lý |
| 1 | `REJECTED` | Message đã được đọc nhưng bị từ chối xử lý |

### 5.3.1. TaskFailureReasonCode

Dùng riêng trong `TaskStatus.reason_code` khi `status_code=FAILED`. Đây là lỗi
phát sinh sau khi robot đã nhận task, không dùng thay cho `AckReasonCode`.

| Giá trị | Tên trong code | Ý nghĩa |
|---:|---|---|
| 0 | `NONE` | Không có nguyên nhân thất bại |
| 1 | `NAVIGATION_FAILED` | Điều hướng thất bại |
| 2 | `TARGET_UNREACHABLE` | Không thể tiếp cận pose đích |
| 3 | `PATH_BLOCKED` | Đường đi bị chặn |
| 4 | `TIMEOUT` | Thực thi quá thời gian |
| 5 | `ROBOT_ERROR` | Robot phát sinh lỗi khi thực thi |
| 6 | `LOCALIZATION_LOST` | Robot mất định vị |
| 7-10 | Lỗi dispatcher | Backend không thể hoàn tất assign/cancel |
| 255 | `UNKNOWN` | Nguyên nhân chưa được nhận diện |

### 5.4. AckReasonCode

Dùng trong `Ack.reason_code` để mô tả nguyên nhân chi tiết.

| Giá trị | Tên trong code | Ý nghĩa |
|---:|---|---|
| 0 | `NONE` | Không có lỗi; thường đi cùng `ACCEPTED` |
| 1 | `ROBOT_BUSY` | Robot đang bận |
| 2 | `ROBOT_ERROR` | Robot đang ở trạng thái lỗi |
| 3 | `INVALID_COMMAND` | Nội dung lệnh không hợp lệ hoặc không được hỗ trợ |
| 4 | `OUT_OF_RANGE` | Pose hoặc tham số nằm ngoài phạm vi cho phép |
| 5 | `DUPLICATE_REFERENCE` | Reference ID đã được dùng cho một message khác |

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

`Ack` phản hồi kết quả tiếp nhận một message quan trọng. Class này dùng chung
cho `TaskAssign`, `TaskCancel`, `TaskStatus` và `MoveToPoint`.

`reference_id` là tên tổng quát cho định danh của message được ACK:

| `acked_type` | Giá trị đặt vào `reference_id` |
|---|---|
| `TASK_ASSIGN` | `TaskAssign.task_id` |
| `TASK_CANCEL` | `TaskCancel.task_id` |
| `TASK_STATUS` | `TaskStatus.task_id` |
| `MOVE_TO_POINT` | `MoveToPoint.move_id` |

Một ACK được đối chiếu bằng bộ khóa
`(robot_id, acked_type, reference_id)`. `reference_id`, `task_id` và `move_id`
đều dùng `uint8`, có miền giá trị từ 0 đến 255.

Format trong code:

```python
FORMAT = "<BBBBBB"
```

Payload:

| Offset | Size | Field | Type | Mô tả |
|---:|---:|---|---|---|
| 0 | 1 | `message_type` | `uint8` | Cố định = `MessageType.ACK` = 4 |
| 1 | 1 | `robot_id` | `uint8` | Robot liên quan tới ACK này |
| 2 | 1 | `acked_type` | `uint8` | Loại message được ACK |
| 3 | 1 | `reference_id` | `uint8` | `task_id` hoặc `move_id`, tùy `acked_type` |
| 4 | 1 | `result_code` | `uint8` | Xem `AckResultCode` |
| 5 | 1 | `reason_code` | `uint8` | Xem `AckReasonCode` |

Kích thước frame truyền qua UART:

| Thành phần | Byte |
|---|---:|
| Start byte `0xAA` | 1 |
| Length | 1 |
| Payload | 6 |
| Checksum | 2 |
| Tổng UART frame | 10 |

Ví dụ ACK chấp nhận `TaskAssign` có `task_id=10` từ robot `1`:

```python
Ack(
    robot_id=1,
    acked_type=MessageType.TASK_ASSIGN,
    reference_id=10,
    result_code=AckResultCode.ACCEPTED,
    reason_code=AckReasonCode.NONE,
)
```

Ví dụ robot đã đọc `MoveToPoint` có `move_id=200` nhưng không thể thực hiện:

```python
Ack(
    robot_id=1,
    acked_type=MessageType.MOVE_TO_POINT,
    reference_id=200,
    result_code=AckResultCode.REJECTED,
    reason_code=AckReasonCode.ROBOT_ERROR,
)
```

`ACCEPTED` chỉ xác nhận robot đã chấp nhận lệnh. Nó không có nghĩa task đã hoàn
thành hoặc robot đã tới pose đích. Lỗi phát sinh sau khi chấp nhận task vẫn được
báo bằng `TaskStatus.FAILED`.

`UartManagerV2.send_with_retry()` trả `True` khi nhận ACK `ACCEPTED`. Khi nhận
ACK `REJECTED`, hàm trả `False` ngay và không lặp lại cùng message trong vòng
retry hiện tại. Nếu chưa nhận ACK, hàm gửi lại theo cấu hình timeout/retry.

ACK mới không tương thích nhị phân với ACK 4-byte cũ. Python và firmware phải
được cập nhật đồng thời trước khi sử dụng schema này.

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
FORMAT = "<BBBBB"
```

Payload:

| Offset | Size | Field | Type | Mô tả |
|---:|---:|---|---|---|
| 0 | 1 | `message_type` | `uint8` | Cố định = `MessageType.TASK_STATUS` = 2 |
| 1 | 1 | `robot_id` | `uint8` | Robot đang báo cáo |
| 2 | 1 | `task_id` | `uint8` | Task được báo cáo |
| 3 | 1 | `status_code` | `uint8` | Xem `TaskStatusCode` |
| 4 | 1 | `reason_code` | `uint8` | Xem `TaskFailureReasonCode`; đặt `NONE` nếu task không FAILED |

Kích thước frame truyền qua UART:

| Thành phần | Byte |
|---|---:|
| Start byte `0xAA` | 1 |
| Length | 1 |
| Payload | 5 |
| Checksum | 2 |
| Tổng UART frame | 9 |

#### Quy tắc gửi TaskStatus

Với mỗi `(robot_id, task_id)`, robot chỉ được có tối đa một `TaskStatus` đang
chờ ACK tại một thời điểm:

```text
Gửi TaskStatus
→ chờ ACK có acked_type=TASK_STATUS
→ nhận ACK thì mới gửi status tiếp theo
→ hết timeout thì gửi lại đúng TaskStatus cũ
```

Quy tắc stop-and-wait này là bắt buộc vì khóa ACK chỉ chứa `robot_id`,
`acked_type` và `reference_id`; chưa có `sequence_id` để phân biệt ACK của
`IN_PROGRESS`, `COMPLETED` hoặc `FAILED` cho cùng một task.

Schema `TaskStatus` 5-byte này không tương thích nhị phân với schema 4-byte cũ;
firmware và Python phải được cập nhật đồng thời.

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

### 7.6. MoveToPoint

`MoveToPoint` là message Dispatcher gửi để yêu cầu robot di chuyển tới một pose
đích. Message dùng `move_id` riêng, không dùng `task_id`. Robot phải phản hồi
bằng `Ack` có `acked_type=MOVE_TO_POINT` và `reference_id=move_id`.

Format trong code:

```python
FORMAT = "<BBBhhh"
```

Payload:

| Offset | Size | Field | Type | Mô tả |
|---:|---:|---|---|---|
| 0 | 1 | `message_type` | `uint8` | Cố định = `MessageType.MOVE_TO_POINT` = 5 |
| 1 | 1 | `robot_id` | `uint8` | Robot nhận lệnh |
| 2 | 1 | `move_id` | `uint8` | ID lệnh di chuyển, 0-255 |
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
MoveToPoint(
    robot_id=1,
    move_id=200,
    x=1.23,
    y=4.56,
    theta=1.57,
)
```

Giá trị raw trước checksum:

| Field | Giá trị logic | Giá trị raw |
|---|---:|---:|
| `message_type` | `MOVE_TO_POINT` | 5 |
| `robot_id` | 1 | 1 |
| `move_id` | 200 | 200 |
| `x` | 1.23 m | 123 |
| `y` | 4.56 m | 456 |
| `theta` | 1.57 rad | 1570 |

Khi Dispatcher gửi lại cùng bộ
`(robot_id, MOVE_TO_POINT, move_id)` do mất ACK, robot không được tạo một lệnh
di chuyển mới. Robot phải nhận diện đây là lần gửi lại và trả lại kết quả tiếp
nhận đã lưu cho `move_id` đó. Robot phải từ chối một `MoveToPoint` mới khi đang
bận; sau khi lệnh hoàn thành và robot trở về `IDLE`, robot xóa `move_id` đã lưu.

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
- Với `MoveToPoint`, lưu kết quả nhận theo `move_id` để retry là idempotent,
  từ chối ID mới khi robot đang bận và xóa ID đã hoàn thành khi trở về `IDLE`.
- Khi Python gửi bằng `UartManagerV2.send_message()`, manager tự thêm `0xAA` +
  `length`. Firmware/bên forward gửi Heartbeat, TaskStatus hoặc ACK về Python
  phải tự thêm cả 2 byte này.
- `length` tối đa 255 (`uint8`). Toàn bộ message hiện tại (payload + checksum)
  đều dưới 20 byte nên còn rất nhiều dư địa.
- Công thức checksum hiện tại là `crc32(payload) & 0xFFFF`, không phải biến thể
  CRC-16/CCITT truyền thống.
- `task_id` hiện tại là `uint8`, tối đa 255. Nếu cần chạy lâu với nhiều task hơn,
  cần đổi `TaskAssign`, `TaskStatus` và `TaskCancel` sang `uint16`.
- `MoveToPoint.move_id` và `Ack.reference_id` là `uint8`, tối đa 255.
- Với ACK của message liên quan tới task, đặt `task_id` vào `reference_id`; với
  ACK của `MoveToPoint`, đặt `move_id` vào `reference_id`.
- `Ack.acked_type` nên dùng đúng giá trị trong `MessageType`.
- Robot phải phân biệt ACK `ACCEPTED` và `REJECTED`; khi `REJECTED`, đặt
  `reason_code` phù hợp thay vì chỉ xác nhận đã nhận byte.
- `TaskStatus` phải tuân theo stop-and-wait: chờ ACK trước khi gửi status tiếp
  theo cho cùng task.
