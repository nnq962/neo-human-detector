import sys
import os

# Thêm thư mục gốc vào PYTHONPATH để có thể import từ src
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from utils import load_config, load_zones, LOGGER
from src.detector import Detector

def main():
    # Đường dẫn tuyệt đối tới file configs/test.yaml
    config_path = os.path.join(PROJECT_ROOT, "configs", "test.yaml")
    
    if not os.path.exists(config_path):
        LOGGER.error(f"Không tìm thấy file cấu hình tại {config_path}")
        return
        
    # Tái sử dụng utils để load config và zone
    cfg = load_config(config_path)
    zones = load_zones(cfg)
            
    # Nạp cấu hình detector
    detector_opts = cfg.get("detector", {})
    
    # Khởi tạo Detector với 1 zone và cấu hình detector
    detector = Detector(
        zones=zones,
        **detector_opts
    )
    
    LOGGER.info("Bắt đầu chạy Detector với cấu hình test.yaml (Bấm Ctrl+C để dừng)...")
    try:
        detector.run()
    except KeyboardInterrupt:
        LOGGER.info("Đã nhận lệnh dừng từ người dùng.")
        detector.stop()

if __name__ == "__main__":
    main()
