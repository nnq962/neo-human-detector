import os
import sys

# Thêm thư mục gốc vào PYTHONPATH để có thể import từ src
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)


def main():
    from src.app import Runtime, build_runtime_config
    from utils import LOGGER

    # Đường dẫn tuyệt đối tới file configs/test.yaml
    config_path = os.path.join(PROJECT_ROOT, "configs", "test.yaml")

    if not os.path.exists(config_path):
        LOGGER.error(f"Không tìm thấy file cấu hình tại {config_path}")
        return

    runtime = Runtime(build_runtime_config(config_path))

    LOGGER.info("Bắt đầu chạy Detector với cấu hình test.yaml (Bấm Ctrl+C để dừng)...")
    try:
        runtime.run()
    except KeyboardInterrupt:
        LOGGER.info("Đã nhận lệnh dừng từ người dùng.")
        runtime.stop()

if __name__ == "__main__":
    main()
