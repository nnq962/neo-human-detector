from human_detector import HumanDetector

# ============================================================
# CẤU HÌNH CHẠY
# ============================================================

# source có thể là:
#   - 0, 1, 2, ...       => USB Camera
#   - "path/to/video.mp4"=> File video
#   - "rtsp://..."       => Stream RTSP camera

# SOURCE = 0  # USB Camera mặc định
# SOURCE = "examples/crowd.mp4"
SOURCE = "rtsp://admin:phenikaaneo%40@10.70.22.159:554/Streaming/Channels/101"

# Chọn mode: "person" hoặc "human_head"
# MODE = "person"
MODE = "human_head"

# (Tùy chọn) Ghi đè đường dẫn model mặc định
# Để None để dùng model mặc định theo mode
MODEL_PATH = None
# MODEL_PATH = "models/person/yolo26n.pt"
# MODEL_PATH = "models/head/yolov8_nano.pt"

# Cách xác định điểm đại diện khi kiểm tra ROI:
#   'center'        — tâm bbox (phù hợp cho đầu người)
#   'bottom_center' — giữa cạnh dưới bbox (phù hợp cho toàn thân người đứng)
ROI_CHECK_MODE = "center"

# ============================================================

if __name__ == "__main__":
    detector = HumanDetector(
        mode=MODE,
        model_path=MODEL_PATH,
        source=SOURCE,
        conf=0.65,
        imgsz=640,
        device=0,           # GPU 0; đổi thành 'cpu' nếu không có GPU
        half=True,          # Dùng FP16 để tăng tốc (tắt đi nếu gặp lỗi)
        show=True,
        roi_check_mode=ROI_CHECK_MODE,
    )

    detector.run()
