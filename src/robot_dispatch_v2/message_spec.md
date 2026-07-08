# Message Spec — Giao tiếp Dispatcher ↔ Robot (qua LoRa)

Tài liệu này mô tả format nhị phân (binary) cho toàn bộ message trao đổi giữa Dispatcher (edge device) và các Robot qua sóng LoRa. Mọi số nhiều byte đều đóng gói theo **little-endian**. Mỗi message kết thúc bằng 2 byte **CRC16** để phát hiện dữ liệu hỏng trên đường truyền — nếu CRC không khớp, bên nhận loại bỏ toàn bộ message, coi như chưa từng nhận được.

> Ghi chú: `detection` (Camera → Dispatcher) không nằm trong tài liệu này vì đây là giao tiếp nội bộ trong edge device, không đi qua LoRa, không cần các cơ chế chống mất gói.

> **Đã bỏ trạng thái `moving` riêng.** Toàn bộ quá trình từ lúc robot nhận task đến khi phục vụ xong được gộp chung vào 1 trạng thái duy nhất: `serving` — không còn phân biệt "đang di chuyển tới nơi" và "đang đứng phục vụ". Áp dụng cho cả `task_status.status` và `heartbeat.state` / `full_state_sync.expected_state`.

---

## 1. Cấu trúc header chung

Mọi message đều bắt đầu bằng 3 byte giống nhau, giúp bên nhận biết ngay đây là loại message gì trước khi parse phần còn lại:

| Offset | Size | Field | Type | Ghi chú |
|---|---|---|---|---|
| 0 | 1 | `msg_type` | uint8 | Xem [Bảng loại message](#2-bảng-loại-message-msg_type) |
| 1 | 2 | `msg_id` | uint16 | Dùng để khớp ACK/retry (heartbeat dùng `seq` riêng thay vì `msg_id`) |
| 3 | 1 | `robot_id` | uint8 | Định danh robot |
| ... | ... | *(payload riêng từng loại)* | | |
| cuối | 2 | `CRC16` | uint16 | Luôn ở 2 byte cuối cùng của message |

---

## 2. Bảng loại message (`msg_type`)

| Giá trị | Tên | Chiều gửi | Cần ACK/Retry? |
|---|---|---|---|
| 1 | `task_assign` | Dispatcher → Robot | ✅ Có — ACK bằng `cmd_ack` |
| 2 | `cmd_ack` | Robot → Dispatcher | Không (dùng heartbeat làm backstop) |
| 3 | `task_status` | Robot → Dispatcher | Nên có, không bắt buộc gắt |
| 4 | `task_cancel` | Dispatcher → Robot | ✅ Có — ACK bằng `cmd_ack` |
| 5 | `heartbeat` | Robot → Dispatcher | Không cần |
| 6 | `full_state_sync` | Dispatcher → Robot | Không cần |
| 7 | `error_report` | Robot → Dispatcher | ✅ Có |

---

## 3. Chi tiết từng loại message

### 3.1. `task_assign` — Dispatcher → Robot

Gửi khi có task ở trạng thái `PENDING` và Dispatcher đã chọn được robot `idle` gần nhất. **Đây là message quan trọng nhất hệ thống** — mất message này đồng nghĩa robot không biết có việc, nên bắt buộc chờ `cmd_ack`, retry nếu timeout.

| Offset | Size | Field | Type | Ghi chú |
|---|---|---|---|---|
| 0 | 1 | `msg_type` | uint8 | = 1 |
| 1 | 2 | `msg_id` | uint16 | |
| 3 | 1 | `robot_id` | uint8 | |
| 4 | 2 | `task_id` | uint16 | |
| 6 | 2 | `x` | int16 | Đơn vị cm |
| 8 | 2 | `y` | int16 | Đơn vị cm |
| 10 | 2 | `CRC16` | uint16 | |
| | **12** | | | **Tổng byte** |

### 3.2. `cmd_ack` — Robot → Dispatcher

**Message ACK dùng chung cho cả `task_assign` và `task_cancel`.** Gửi ngay sau khi robot nhận và xử lý 1 trong 2 lệnh đó. Không cần ACK riêng cho chính message này (tránh vòng lặp ACK-cho-ACK vô hạn) — dựa vào `heartbeat` (mục 3.5) làm lớp đối chiếu backstop nếu message này bị mất trên đường về.

Vì dùng chung cho 2 loại lệnh, bên nhận (Dispatcher) xác định `cmd_ack` này đang phản hồi cho lệnh nào bằng cách **tra `msg_id`** trong bảng "các lệnh đang chờ ACK" mà Dispatcher vốn đã phải giữ sẵn để phục vụ cơ chế retry — không cần thêm field phân biệt loại lệnh.

| Offset | Size | Field | Type | Ghi chú |
|---|---|---|---|---|
| 0 | 1 | `msg_type` | uint8 | = 2 |
| 1 | 2 | `msg_id` | uint16 | Echo lại `msg_id` của lệnh gốc (`task_assign` HOẶC `task_cancel`) |
| 3 | 1 | `robot_id` | uint8 | |
| 4 | 2 | `task_id` | uint16 | |
| 6 | 1 | `result_code` | uint8 | Xem [bảng result_code](#42-result_code-cmd_ack) |
| 7 | 2 | `CRC16` | uint16 | |
| | **9** | | | **Tổng byte** |

> **Lưu ý race condition**: khi ACK cho `task_cancel`, có thể xảy ra tình huống Dispatcher gửi lệnh hủy đúng lúc robot vừa phục vụ xong task đó. Đây là lý do có `result_code = 4 (already_done)` — để Dispatcher phân biệt "hủy thành công" với "hủy trễ, task đã hoàn thành trước khi lệnh cancel kịp đến", tránh đóng nhầm task thành `CANCELLED` dù thực ra đã `SERVED`.

### 3.3. `task_status` — Robot → Dispatcher

Gửi khi robot chuyển trạng thái thực thi task: bắt đầu xử lý task (`serving` — bao gồm cả lúc đang di chuyển tới nơi lẫn lúc đã đến và đang trao nước) / phục vụ xong (`done`). Nên gửi tin cậy nhưng không cần retry quá gắt — nếu mất, chu kỳ `heartbeat` tiếp theo vẫn phản ánh đúng trạng thái thật.

| Offset | Size | Field | Type | Ghi chú |
|---|---|---|---|---|
| 0 | 1 | `msg_type` | uint8 | = 3 |
| 1 | 2 | `msg_id` | uint16 | |
| 3 | 1 | `robot_id` | uint8 | |
| 4 | 2 | `task_id` | uint16 | |
| 6 | 1 | `status` | uint8 | 0=serving, 1=done |
| 7 | 4 | `timestamp` | uint32 | Unix time (giây) |
| 11 | 2 | `CRC16` | uint16 | |
| | **13** | | | **Tổng byte** |

### 3.4. `task_cancel` — Dispatcher → Robot

Gửi khi cần hủy task đã gán (VD: phát hiện trùng lặp 2 robot cùng 1 chỗ, hoặc camera thấy ghế đã trống trước khi robot tới). Quan trọng không kém `task_assign` — mất message này thì robot cứ tiếp tục đi phục vụ chỗ đã trống hoặc đã có robot khác lo, nên cần độ tin cậy tương đương (ACK bằng `cmd_ack` + retry).

| Offset | Size | Field | Type | Ghi chú |
|---|---|---|---|---|
| 0 | 1 | `msg_type` | uint8 | = 4 |
| 1 | 2 | `msg_id` | uint16 | |
| 3 | 1 | `robot_id` | uint8 | |
| 4 | 2 | `task_id` | uint16 | |
| 6 | 1 | `reason_code` | uint8 | Lý do hủy. Xem [bảng cancel_reason_code](#43-cancel_reason_code-task_cancel) |
| 7 | 2 | `CRC16` | uint16 | |
| | **9** | | | **Tổng byte** |

### 3.5. `heartbeat` — Robot → Dispatcher

Gửi định kỳ (khuyến nghị mỗi 3-5s, cộng thêm jitter ngẫu nhiên để tránh đụng độ giữa các robot cùng kênh LoRa). Không cần ACK/retry — mất 1 lần thì lần sau tự có bản mới. Đây là **lớp đối chiếu (reconciliation)** cho toàn hệ thống, bù đắp khi các message ở trên bị mất (VD: phát hiện robot thực ra đã nhận task dù `cmd_ack` bị rớt).

|   Offset |   Size | Field       | Type     | Ghi chú                                                   |
| -------: | -----: | ----------- | -------- | --------------------------------------------------------- |
|        0 |      1 | `msg_type`  | `uint8`  | = 5                                                       |
|        1 |      2 | `seq`       | `uint16` | Số thứ tự riêng của heartbeat (không dùng chung `msg_id`) |
|        3 |      1 | `robot_id`  | `uint8`  |                                                           |
|        4 |      4 | `timestamp` | `uint32` |                                                           |
|        8 |      2 | `x`         | `int16`  | m                                                         |
|       10 |      2 | `y`         | `int16`  | m                                                         |
|       12 |      2 | `theta`     | `int16`  | rad                                                       |
|       14 |      1 | `state`     | `uint8`  | Xem bảng state                                            |
|       15 |      2 | `task_id`   | `uint16` | `0` = không có task                                       |
|       17 |      2 | `CRC16`     | `uint16` |                                                           |
| **Tổng** | **19** |             |          | **byte**                                                  |


### 3.6. `full_state_sync` — Dispatcher → Robot *(khuyến nghị thêm)*

Gửi định kỳ, chu kỳ dài hơn heartbeat (VD 10-15s). Không cần ACK — bản chất tự ghi đè, lần sau lại gửi tiếp. Là **lớp bảo hiểm cuối cùng**: nếu cả `task_assign` lẫn các lần retry đều thất bại hết, message này vẫn kéo robot về đúng trạng thái Dispatcher mong đợi.

| Offset | Size | Field | Type | Ghi chú |
|---|---|---|---|---|
| 0 | 1 | `msg_type` | uint8 | = 6 |
| 1 | 2 | `msg_id` | uint16 | |
| 3 | 1 | `robot_id` | uint8 | |
| 4 | 2 | `expected_task_id` | uint16 | 0 = không có task nào đang mong đợi |
| 6 | 1 | `expected_state` | uint8 | Robot nên ở state nào theo góc nhìn Dispatcher. Xem [bảng state](#41-state-heartbeat) |
| 7 | 2 | `x` | int16 | Vị trí task (nếu có), cm |
| 9 | 2 | `y` | int16 | cm |
| 11 | 2 | `CRC16` | uint16 | |
| | **13** | | | **Tổng byte** |

### 3.7. `error_report` — Robot → Dispatcher

Gửi khi có sự kiện lỗi cụ thể xảy ra (kẹt bánh, va chạm, mất định vị...). Cần ACK/retry vì đây là thông tin cần hành động ngay (hủy task, gọi người can thiệp) — không nên gộp chung với heartbeat vì cần được xử lý ưu tiên, không đợi đúng chu kỳ định kỳ.

| Offset | Size | Field | Type | Ghi chú |
|---|---|---|---|---|
| 0 | 1 | `msg_type` | uint8 | = 7 |
| 1 | 2 | `msg_id` | uint16 | |
| 3 | 1 | `robot_id` | uint8 | |
| 4 | 1 | `error_code` | uint8 | Xem [bảng error_code](#44-error_code) |
| 5 | 2 | `task_id` | uint16 | 0 nếu không đang làm task nào |
| 7 | 2 | `CRC16` | uint16 | |
| | **9** | | | **Tổng byte** |

---

## 4. Bảng mã dùng chung

Các bảng này dùng chung cho cả team Dispatcher lẫn team firmware Robot — cần thống nhất tuyệt đối, không tự ý đổi giá trị.

### 4.1. `state` (heartbeat / full_state_sync)

Không còn `moving` riêng — robot đang di chuyển đến chỗ khách hay đang trao nước đều báo chung là `serving`.

| Giá trị | Ý nghĩa |
|---|---|
| 0 | idle |
| 1 | serving |
| 2 | returning |
| 3 | error |

### 4.2. `result_code` (cmd_ack)

Dùng chung cho ACK của cả `task_assign` và `task_cancel`.

| Giá trị | Ý nghĩa | Áp dụng cho |
|---|---|---|
| 0 | OK — đồng ý nhận task / đã hủy thành công | Cả 2 |
| 1 | low_battery — từ chối vì pin yếu | `task_assign` |
| 2 | busy — đang bận task khác | `task_assign` |
| 3 | nav_error — lỗi định vị/di chuyển | `task_assign` |
| 4 | already_done — task đã hoàn thành xong trước khi lệnh cancel kịp đến | `task_cancel` |
| 5 | unknown_task — robot không có bản ghi `task_id` này | Cả 2 |

### 4.3. `cancel_reason_code` (task_cancel)

| Giá trị | Ý nghĩa |
|---|---|
| 0 | duplicate |
| 1 | seat_empty |
| 2 | manual_override |

### 4.4. `error_code`

| Giá trị | Ý nghĩa |
|---|---|
| 0 | không lỗi |
| 1 | kẹt bánh xe / va chạm |
| 2 | mất định vị (lost localization) |
| 3 | pin yếu nghiêm trọng |
| 4 | bị điều khiển tay (manual override) |

---

## 5. Lưu ý triển khai

- **Endianness**: tất cả số nhiều byte đóng gói theo **little-endian**. Cần xác nhận với team IoT rằng vi điều khiển (ESP32/STM32/...) xử lý đúng theo chiều này.
- **CRC16**: cả 2 phía phải dùng chung đúng 1 biến thể (VD: CRC-16/CCITT-FALSE, poly=0x1021, init=0xFFFF, xorOut=0x0000). Dùng lệch biến thể sẽ khiến dữ liệu đúng vẫn báo sai liên tục.
- **Giới hạn giá trị**:
  - `x`, `y` (int16, cm): biểu diễn được từ -327.68m đến +327.67m — đủ dư cho phạm vi 1 sảnh. Nếu không gian rộng hơn, cần đổi sang int32.
  - `task_id` (uint16): tối đa 65,535 task — đủ cho hệ thống chạy nhiều tháng liên tục không tràn số.
- **Message quan trọng, cần ACK + retry** (mất là hỏng quy trình): `task_assign`, `task_cancel`, `error_report`.
- **Message tự làm mới định kỳ, không cần ACK** (mất 1 lần không sao, lần sau tự có bản mới): `heartbeat`, `full_state_sync`.
- **`heartbeat.state` + `heartbeat.task_id`** không dùng để trigger hành động mới, chỉ dùng để đối chiếu (reconciliation) — phát hiện lệch trạng thái do message trước đó bị mất, và tự đồng bộ lại.
- **`cmd_ack` dùng chung cho 2 lệnh**: Dispatcher phân biệt ACK này ứng với `task_assign` hay `task_cancel` bằng cách tra `msg_id` trong bảng lệnh đang chờ ACK (đã có sẵn cho cơ chế retry) — không cần thêm field phân loại. Đừng bỏ sót `result_code = 4 (already_done)` khi xử lý ACK của `task_cancel`, vì đây là race condition thực tế dễ gặp khi hệ thống chạy dài ngày.
- **Đã bỏ trạng thái `moving`**: nếu sau này cần phát hiện robot bị kẹt/lạc đường giữa lúc di chuyển (so với lúc đang đứng phục vụ), sẽ cần tách lại 2 trạng thái này — hiện tại đơn giản hóa vì không cần độ chi tiết đó.
