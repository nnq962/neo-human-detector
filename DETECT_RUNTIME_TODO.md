# Detect Runtime TODO

Ghi chú các việc cần làm tiếp sau khi đọc logic `DetectOnlyRuntime.run()` trong
`src/app/detect_runtime.py`.

## 1. Tổng Quan

`DetectOnlyRuntime.run()` hiện đang điều phối toàn bộ flow:

- Chuẩn bị camera, zone, YOLO detector, zone state machine và optional ReID.
- Chọn stream YOLO detect-only hoặc ByteTrack tracking.
- Gán detection vào zone, cập nhật trạng thái zone.
- Chạy ReID nếu bật, enrich detection bằng `global_id/status/similarity`.
- Cập nhật occupancy, sinh `RobotServiceRequest` nếu đủ điều kiện.
- Cập nhật snapshot WebSocket và preview OpenCV nếu `show=True`.
- Cleanup detector/OpenCV khi loop kết thúc.

Các việc tiếp theo nên tập trung vào test tự động, kiểm chứng ReID, chống mất
robot request, và hardening cleanup/state reset.

## 2. Ưu Tiên Cao

### P0 - Thêm test runtime với fake stream

Hiện thư mục `tests/` chủ yếu là script chạy tay, chưa có test tự động cho
`DetectOnlyRuntime`.

Cần tạo unit/integration test có mock/fake:

- Fake `YoloDetector.predict_stream()` và `track_stream()` để yield
  `DetectionFrame` theo kịch bản.
- Fake camera + zone để kiểm tra mapping `result_index % len(cameras)`.
- Fake `ReIdPipeline` để trả assignment gồm `global_id`, `similarity`,
  `status=confirmed`.
- Fake/patch clock nếu cần test zone state machine theo thời gian.

Kịch bản nên cover:

- `use_tracking=False`, ReID off -> runtime dùng `predict_stream()`.
- `use_tracking=True` hoặc ReID on -> runtime dùng `track_stream()`.
- Detection trong zone làm zone đi từ `EMPTY` -> `PENDING_ENTER` -> `OCCUPIED`.
- Khi `require_occupied_zone=True`, ReID chỉ xử lý detection nằm trong zone đã
  `OCCUPIED`.
- Sau ReID confirmed, occupancy tạo `RobotServiceRequest`.
- `stop()` luôn close detector và mark runtime stopped khi loop kết thúc.

### P0 - Chống mất robot request

Hiện `RuntimeState.update_robot_requests()` chỉ lưu request của frame mới nhất.
Nếu consumer đọc chậm, request có thể bị miss khi frame sau cập nhật thành list
rỗng.

Hướng xử lý:

- Đổi `latest_robot_requests` thành queue/outbox có acknowledge; hoặc
- Dispatch request ngay khi sinh ra sang robot sender; hoặc
- Lưu lịch sử request ngắn hạn kèm `request_id` để consumer không miss.

Cần thêm test:

- Request không bị gửi lặp cho cùng `global_id` đã `REQUESTED`.
- Request không mất nếu frame kế tiếp không có request mới.
- Có cách mark `SERVED` và reset identity rõ ràng.

### P0 - Cleanup nếu `_prepare()` lỗi

Trong `run()`, `_prepare()` hiện nằm trước block `try/finally`. Nếu lỗi xảy ra
sau khi một phần tài nguyên đã được khởi tạo, `stop()` có thể không được gọi.

Hướng xử lý:

- Đưa `_prepare()` vào trong `try`; hoặc
- Bọc cleanup riêng khi `_prepare()` fail.

Cần test:

- Fake `_prepare()` tạo detector rồi raise exception, runtime vẫn close detector.

## 3. Ưu Tiên Trung Bình

### P1 - Reset state khi chạy lại cùng runtime object

`RuntimeState.reset()` được gọi, nhưng các state khác có thể vẫn còn:

- `zone_occupancy_manager.identity_states`
- `zone_occupancy_manager.latest_snapshot`
- `_prev_times_by_camera`

Rủi ro:

- Run lần sau không tạo robot request vì `global_id` cũ đã `REQUESTED`.
- FPS frame đầu lần sau tính sai.

Hướng xử lý:

- Reset/recreate `ZoneOccupancyManager` trong `_prepare()`.
- Clear `_prev_times_by_camera` trong `_prepare()` hoặc `stop()`.

### P1 - Validate source YOLO khớp camera config

Runtime load camera/zone từ YAML, nhưng YOLO source lấy từ `self.config.source`,
mặc định `configs/rtsp.streams`.

Rủi ro:

- YAML đổi camera source nhưng `configs/rtsp.streams` không được cập nhật.
- Thứ tự stream trong file khác thứ tự camera enabled trong YAML.
- `result_index % len(cameras)` gán frame vào sai camera/zone.

Hướng xử lý:

- Trong `_prepare()`, build/write streams file từ list camera enabled; hoặc
- Validate source file có cùng số lượng và thứ tự với camera config.

### P1 - Làm rõ ý nghĩa `max_frames`

Với nhiều camera, `max_frames` là tổng số result từ Ultralytics, không phải số
frame mỗi camera.

Cần làm:

- Ghi rõ trong CLI help/log.
- Nếu cần test theo camera, thêm option `max_frames_per_camera`.

## 4. Rủi Ro ReID Cần Kiểm Chứng

### ReID có thể xác nhận rất trễ

Với config hiện tại:

- Zone cần `confirm_enter_time` trước khi `OCCUPIED`.
- Nếu `require_occupied_zone=True`, ReID chỉ bắt đầu sau khi zone đã occupied.
- ReID mặc định cần `stable_bbox_window=100` và `buffer_min=200` crop tốt trước
  khi `confirmed`.

Hệ quả:

- Chạy `--max-frames` nhỏ có thể không bao giờ thấy `global_id/status=confirmed`.
- Robot request có thể xuất hiện muộn hơn kỳ vọng, tùy FPS và độ ổn định bbox.

Để test nhanh nên tạo config riêng:

- `confirm_enter_time: 0`
- `confirm_exit_time` nhỏ
- `stable_bbox_window` nhỏ
- `buffer_min` nhỏ
- `gallery_ttl_minutes` phù hợp với bài test

### Camera không có zone sẽ không có ReID khi `zone_only=True`

Nếu camera không có zone:

- Detection vẫn có thể hiện trong payload.
- ReID candidate sẽ không được chọn nếu `zone_only=True`.
- Robot request sẽ không sinh ra.

Cần xác định đây là hành vi mong muốn hay cần fallback policy.

## 5. `.gitignore` Nên Theo Dõi

Đã bổ sung các nhóm ignore nên có:

- Python cache/build: `__pycache__/`, `*.py[cod]`, `.pytest_cache/`,
  `.ruff_cache/`, `build/`, `dist/`, `*.egg-info/`.
- Virtual environment: `.venv/`, `venv/`, `env/`, `.env/`.
- Secret/local config: `.env`, `.env.*`, `config.json`, `device.txt`,
  `configs/rtsp.streams`.
- IDE/OS: `.DS_Store`, `.idea/`, `.vscode/`.
- Log/runtime output: `*.log`, `logs/`, `tmp/`, `outputs/`, `runs/`.
- Frontend: `frontend/node_modules/`, `frontend/dist/`, `frontend/.vite/`,
  `frontend/.env*`.
- Model/media artifacts: `/weights/`, `/models/`, `*.pt`, `*.pth`, `*.onnx`,
  `*.engine`, `*.mp4`, `*.avi`, `*.mov`, `*.mkv`.

Lưu ý quan trọng: `.gitignore` chỉ ngăn file chưa tracked bị add mới. Nếu file
đã được Git track trước đó, ví dụ `configs/rtsp.streams` hoặc weight/model file,
cần cân nhắc `git rm --cached <path>` ở một commit riêng để Git ngừng track file
đó.

## 6. Kiểm Thử Thực Tế Đề Xuất

Chạy detect only:

```bash
python tests/detect_app.py --config configs/test.yaml --no-show --max-frames 100
```

Chạy ByteTrack:

```bash
python tests/detect_app.py --config configs/test.yaml --track --no-show --max-frames 200
```

Chạy ReID:

```bash
python tests/detect_app.py --config configs/test.yaml --reid --no-show --max-frames 1000
```

Lưu ý: với ngưỡng ReID mặc định, `max_frames` có thể cần lớn hơn nhiều mới thấy
identity `confirmed`.

## 7. Lộ Trình Đề Xuất

1. Thêm test fake stream cho detect-only và tracking.
2. Thêm test zone state + ReID candidate policy.
3. Sửa cleanup khi `_prepare()` lỗi.
4. Sửa cơ chế robot request thành queue/outbox hoặc dispatch trực tiếp.
5. Reset đầy đủ runtime state khi chạy lại cùng object.
6. Validate/generate `configs/rtsp.streams` từ camera config.
7. Chạy test thực tế với config ReID rút gọn ngưỡng, sau đó mới tăng ngưỡng về
   gần production.
