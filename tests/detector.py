import os
import sys

# Thêm thư mục gốc vào PYTHONPATH để có thể import từ src
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

def main():
    from src.detector import Detector
    from src.camera import load_cameras_from_config
    from utils import LOGGER, load_config

    # Đường dẫn tuyệt đối tới file configs/test.yaml
    config_path = os.path.join(PROJECT_ROOT, "configs", "test.yaml")
    
    if not os.path.exists(config_path):
        LOGGER.error(f"Không tìm thấy file cấu hình tại {config_path}")
        return
        
    # Tái sử dụng config loader cũ và camera loader mới trong src/camera.
    cfg = load_config(config_path)
    cameras = load_cameras_from_config(cfg)
            
    # Nạp cấu hình detector
    detector_opts = cfg.get("detector", {})
    detector_opts.update(cfg.get("zones_state_machine", {}))
    streams_file = cfg.get("source", {}).get("streams_file")
    if streams_file:
        detector_opts["source"] = streams_file
    
    # Khởi tạo Detector với danh sách camera và cấu hình detector
    detector = Detector(
        cameras=cameras,
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
