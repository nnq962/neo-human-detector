# NEO Human Detector

Ứng dụng phát hiện người theo nhiều camera, quản lý vùng giám sát, ReID, UART
và cấu hình thiết bị qua giao diện web.

Ứng dụng chính chạy bằng FastAPI tại port `9721`. Frontend React sau khi build
được FastAPI phục vụ cùng địa chỉ.

## Trạng thái nền tảng

| Nền tảng | Trạng thái | Model |
| --- | --- | --- |
| Ubuntu/Debian PC x86_64 | Không hỗ trợ trong branch này | PyTorch |
| NVIDIA Jetson JP 5.1.6 aarch64 | Đã hỗ trợ setup tự động | PyTorch CUDA |
| RK3588/RKNN | Đã khai báo artifact, runtime chưa hỗ trợ | RKNN |

> Branch này chỉ khóa runtime Jetson aarch64 với Python 3.8. Nội dung PC phía
> dưới được giữ làm tài liệu tham khảo cho branch PC, không chạy
> `scripts/setup-pc.sh` trong branch này.

## Yêu cầu cho PC

- Ubuntu hoặc Debian x86_64.
- Quyền `sudo` để cài system package.
- Git và kết nối Internet.
- Docker với Docker Compose plugin để chạy MediaMTX.
- Node.js `>=20.19`, `>=22.12` hoặc phiên bản mới hơn.
- Thiết bị UART nếu sử dụng robot.

Python 3.10 và `uv` sẽ được script setup chuẩn bị nếu máy chưa có.

## Cài đặt nhanh trên PC

### 1. Clone project

```bash
git clone git@github.com:nnq962/neo-human-detector.git
cd neo-human-detector
```

### 2. Chuẩn bị frontend env

```bash
cp frontend/.env.example frontend/.env
nano frontend/.env
```

Nội dung:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:9721
```

- Khi chạy `npm run dev`, `VITE_API_BASE_URL` là địa chỉ backend mà Vite proxy
  request API và WebSocket tới.
- Khi chạy bản production bằng `scripts/run.sh`, frontend sử dụng API
  same-origin tại port `9721`.

Mật khẩu quản trị không nằm trong frontend env hoặc JavaScript bundle. Setup sẽ
yêu cầu nhập mật khẩu và ghi trực tiếp vào `configs/default.yaml`. Với môi
trường cài đặt không tương tác, truyền mật khẩu qua secret environment
`NEO_CONFIG_PASSWORD` khi chạy setup.

### 3. Khởi động MediaMTX

```bash
docker compose -f mediamtx/docker-compose.yml up -d
```

Kiểm tra container:

```bash
docker ps
curl http://127.0.0.1:9997/v3/config/global/get
```

MediaMTX sử dụng `network_mode: host`, vì vậy cột `PORTS` trong `docker ps`
có thể để trống.

Các port mặc định:

| Dịch vụ | Port |
| --- | ---: |
| NEO API và frontend | `9721` |
| MediaMTX API | `9997` |
| MediaMTX WebRTC HTTP | `8889` |
| MediaMTX WebRTC ICE | `8189` |

### 4. Chạy setup

```bash
./scripts/setup-pc.sh
```

Script sẽ:

1. Kiểm tra Ubuntu/Debian x86_64.
2. Cài FFmpeg, GStreamer và OpenCV runtime libraries.
3. Cài `uv` và chuẩn bị Python 3.10.
4. Tải OpenCV GStreamer wheel từ Google Drive nếu chưa có.
5. Kiểm tra SHA-256 của wheel.
6. Tạo `configs/default.yaml` từ file example nếu chưa có.
7. Đồng bộ Python dependencies từ `uv.lock`.
8. Cấu hình password hash quản trị nếu chưa có.
9. Tải các model PC còn thiếu và kiểm tra SHA-256.
10. Cài frontend dependencies và build frontend.
11. Kiểm tra OpenCV có `GStreamer: YES`.
12. Tùy chọn cài Supervisor nếu truyền `--with-supervisor`.

Các file được tạo/tải tại máy local và không được push lên Git:

```text
configs/default.yaml
frontend/.env
wheels/
weights/
frontend/dist/
```

### 5. Cấp quyền UART

Nếu sử dụng `/dev/ttyUSB0`:

```bash
sudo usermod -aG dialout "$USER"
```

Sau đó đăng xuất và đăng nhập lại. Kiểm tra:

```bash
ls -l /dev/ttyUSB*
id -nG
```

Cổng UART không cần tồn tại trong lúc setup. Có thể thay đổi port sau trên giao
diện web hoặc trong `configs/default.yaml`.

### 6. Kiểm tra và chạy

Chỉ kiểm tra:

```bash
./scripts/run.sh --check
```

Chạy ứng dụng:

```bash
./scripts/run.sh
```

Mở trên chính máy đang chạy:

```text
http://127.0.0.1:9721
```

Mở từ máy khác trong cùng mạng:

```text
http://<IP-của-thiết-bị>:9721
```

Dashboard và các API cấu hình yêu cầu đăng nhập. Màn hình `/live` là public theo
thiết kế và không yêu cầu mật khẩu.

Dừng ứng dụng bằng `Ctrl+C`.

## Cài đặt trên Jetson JetPack 5.1.6

Script Jetson dành riêng cho L4T R35.6.4, aarch64 và system Python 3.8.
`pyproject.toml` và `uv.lock` chỉ resolve Python 3.8 trên Linux aarch64.

Chuẩn bị `frontend/.env` giống hướng dẫn PC, sau đó chạy:

```bash
./scripts/setup-jetson.sh
```

Script sẽ:

1. Xác minh JetPack 5.1.6 và L4T R35.6.4.
2. Cài OpenBLAS, OpenMPI, FFmpeg, GStreamer và compiler cần thiết.
3. Tạo `.venv` và chạy `uv sync --locked` bằng Python 3.8.
4. Tải và kiểm tra checksum các wheel OpenCV, torch và torchvision aarch64.
5. Cài torch/torchvision NVIDIA và OpenCV có GStreamer.
6. Tải model `jetson-aarch64`, build frontend và kiểm tra CUDA.

Chỉ kiểm tra rồi chạy ứng dụng:

```bash
./scripts/run.sh --check
./scripts/run.sh
```

## Chạy tự động bằng Supervisor

Supervisor là tùy chọn. Setup mặc định không cài, không tạo service và không
thay đổi cách chạy thủ công.

Để cài Supervisor và đăng ký ứng dụng tự khởi động:

```bash
./scripts/setup-pc.sh --with-supervisor
```

Setup sẽ render config từ:

```text
deploy/supervisor/neo-human-detector.conf.template
```

Config thực tế được cài tại:

```text
/etc/supervisor/conf.d/neo-human-detector.conf
```

Các lệnh quản lý:

```bash
sudo supervisorctl status neo-human-detector
sudo supervisorctl restart neo-human-detector
sudo supervisorctl stop neo-human-detector
sudo supervisorctl start neo-human-detector
```

Theo dõi log:

```bash
tail -f logs/supervisor.log
```

Sau khi thay code hoặc config Supervisor:

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl restart neo-human-detector
```

Supervisor chạy `scripts/run.sh`, tự khởi động lại khi process crash và gửi
`SIGINT` khi stop để runtime, UART và camera được đóng sạch. Trước khi bật
Supervisor, hãy dừng mọi instance đang chạy thủ công trên port `9721`.

## Cấu hình ứng dụng

Config runtime được lưu tại:

```text
configs/default.yaml
```

File mẫu an toàn:

```text
configs/default.example.yaml
```

Setup không ghi đè `configs/default.yaml` đã tồn tại. Có thể cấu hình camera,
zone, detection, ReID và UART trực tiếp trên giao diện web.

Một số trường chính:

```yaml
web:
  auth:
    enabled: true
    password: 'mat-khau-quan-tri'
    session_ttl_seconds: 28800
  allowed_origins:
    - http://127.0.0.1:5173
    - http://localhost:5173

runtime:
  auto_start: false
  camera_ids: [camera-a, camera-b]

detection:
  model_id: yolo26m-pose-pytorch
  conf: 0.5

reid:
  enabled: false
  model_id: osnet-ain-ms-d-c-pytorch

uart:
  port: /dev/ttyUSB0
  baudrate: 115200

cameras: []
```

Đổi mật khẩu quản trị:

```bash
uv run --locked python scripts/set-web-password.py
```

Khi nâng cấp từ bản dùng `password_hash`, hãy chạy lệnh trên để đặt lại
`web.auth.password`. Hash cũ không thể chuyển ngược thành mật khẩu gốc.

Đổi hash sẽ vô hiệu hóa các session hiện có trong process API.

Batch detection được suy ra từ số phần tử trong `runtime.camera_ids`. Runtime
chỉ hỗ trợ lựa chọn 1, 2 hoặc 4 camera; danh sách `cameras` vẫn có thể chứa nhiều
camera hơn để quản lý và xem stream độc lập.

## Artifact và model

### OpenCV wheel

OpenCV wheel được khai báo trong:

```text
configs/artifacts.yaml
```

Tải hoặc kiểm tra thủ công:

```bash
uv run --no-project \
  --with 'gdown>=5.2.2' \
  --with 'pyyaml>=6.0.3' \
  python scripts/sync-artifacts.py \
  --platform pc-x86_64
```

Chỉ kiểm tra:

```bash
uv run --no-project \
  --with 'gdown>=5.2.2' \
  --with 'pyyaml>=6.0.3' \
  python scripts/sync-artifacts.py \
  --platform pc-x86_64 \
  --check
```

### Model weights

Catalog model và Google Drive ID được khai báo trong:

```text
configs/weights.yaml
```

Đồng bộ model cho nền tảng hiện tại:

```bash
uv run --locked python scripts/sync-models.py
```

Đồng bộ rõ platform:

```bash
uv run --locked python scripts/sync-models.py \
  --platform pc-x86_64
```

Chỉ kiểm tra model:

```bash
uv run --locked python scripts/sync-models.py \
  --platform pc-x86_64 \
  --check
```

Tải lại file có checksum sai:

```bash
uv run --locked python scripts/sync-models.py \
  --platform pc-x86_64 \
  --force
```

Model chỉ xuất hiện trên giao diện khi:

- Entry tồn tại trong `configs/weights.yaml`.
- File tương ứng đã có trong `weights/`.
- Entry có `runtime_supported: true`.

## Các tùy chọn script

### Setup PC

```bash
./scripts/setup-pc.sh --help
```

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `--skip-system-packages` | Không chạy `apt-get` |
| `--skip-frontend` | Không cài và build frontend |
| `--skip-models` | Không kiểm tra hoặc tải model |
| `--with-supervisor` | Cài và chạy app bằng Supervisor |

### Setup Jetson

```bash
./scripts/setup-jetson.sh --help
```

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `--skip-system-packages` | Không chạy `apt-get` |
| `--skip-frontend` | Không cài và build frontend |
| `--skip-models` | Không kiểm tra hoặc tải model |

### Chạy ứng dụng

```bash
./scripts/run.sh --help
```

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `--check` | Chỉ chạy preflight, không mở ứng dụng |
| `--skip-model-sync` | Không kiểm tra hoặc tải model trước khi chạy |

## Phát triển frontend

Chạy backend tại terminal thứ nhất:

```bash
uv run --locked python main.py
```

Chạy Vite tại terminal thứ hai:

```bash
cd frontend
npm run dev
```

Mở:

```text
http://127.0.0.1:5173
```

Nếu Vite báo `504 Outdated Optimize Dep`:

```bash
npm run dev -- --force
```

Sau đó hard refresh trình duyệt bằng `Ctrl+Shift+R`.

## Kiểm thử

Backend:

```bash
uv run --locked python -m pytest -q
```

Kiểm tra UART thật được tách khỏi pytest để không tự mở serial khi collect test:

```bash
uv run --locked python scripts/manual-uart-v2.py
```

Kiểm tra các module setup và model catalog:

```bash
uv run --locked ruff check \
  src/model_catalog.py \
  scripts/*.py \
  tests/test_model_catalog.py
```

Frontend:

```bash
cd frontend
npm run check
```

Preflight đầy đủ:

```bash
./scripts/run.sh --check
```

## Cập nhật project trên thiết bị

```bash
git pull
./scripts/setup-pc.sh
./scripts/run.sh --check
./scripts/run.sh
```

Setup giữ nguyên `configs/default.yaml` và `frontend/.env` hiện có.

## Xử lý sự cố

### Không lưu được config

Kiểm tra quyền:

```bash
ls -l configs/default.yaml
ls -ld configs
```

Sửa owner nếu file từng được tạo bởi root hoặc Docker:

```bash
sudo chown "$USER":"$USER" configs/default.yaml
sudo chown "$USER":"$USER" configs
```

### Không mở được UART

```bash
ls -l /dev/ttyUSB*
sudo usermod -aG dialout "$USER"
```

Đăng xuất/đăng nhập lại sau khi thêm group. Đồng thời kiểm tra không có process
khác đang giữ cổng UART.

### MediaMTX container chạy nhưng API không phản hồi

```bash
docker logs mediamtx-server
curl http://127.0.0.1:9997/v3/config/global/get
```

Khởi động lại:

```bash
docker compose -f mediamtx/docker-compose.yml restart
```

### Model thiếu hoặc sai checksum

```bash
uv run --locked python scripts/sync-models.py \
  --platform pc-x86_64 \
  --force
```

### Frontend build thiếu env

```bash
cp frontend/.env.example frontend/.env
nano frontend/.env
./scripts/setup-pc.sh --skip-system-packages
```

## Bảo mật và file local

- Không commit `configs/default.yaml`; file này có thể chứa RTSP credential,
  thông tin thiết bị và mật khẩu quản trị dạng plaintext.
- Không commit `frontend/.env`.
- Không commit wheel hoặc weights trực tiếp; chúng được tải qua manifest.
- Google Drive artifact phải được chia sẻ ở chế độ người có link có thể xem.
- Khi thay artifact, cần cập nhật cả `drive_id` và `sha256`.
- Dashboard dùng session ngẫu nhiên lưu phía server và cookie `HttpOnly`,
  `SameSite=Strict`; các request ghi và WebSocket riêng tư được kiểm tra Origin.
- `/live` và `/api/public/*` là public theo thiết kế. Chúng có thể hiển thị danh
  sách camera, WHEP stream, zone, bbox, calibration và vị trí/trạng thái robot;
  không trả RTSP source hoặc cho phép sửa cấu hình.

## Cấu trúc liên quan đến setup

```text
configs/
├── artifacts.yaml         # OpenCV wheel và artifact bootstrap
├── default.example.yaml   # Runtime config mẫu
└── weights.yaml           # Catalog model và Google Drive ID

frontend/
└── .env.example           # Frontend env mẫu

mediamtx/
├── docker-compose.yml
└── mediamtx.yml

scripts/
├── run.sh
├── set-web-password.py
├── setup-pc.sh
├── sync-artifacts.py
└── sync-models.py

deploy/supervisor/
└── neo-human-detector.conf.template

weights/                   # Model local, không theo dõi bởi Git
wheels/                    # Wheel local, không theo dõi bởi Git
```
