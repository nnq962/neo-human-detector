import json
from human_detector import HumanDetector

# ============================================================
# CẤU HÌNH CHẠY (LOAD TỪ CONFIG.JSON)
# ============================================================
CONFIG_FILE = "config.json"

def load_config(file_path):
    with open(file_path, 'r') as f:
        return json.load(f)

if __name__ == "__main__":
    config = load_config(CONFIG_FILE)

    detector = HumanDetector(
        source=config.get("source", 0),
        conf=config.get("conf", 0.5),
        imgsz=config.get("imgsz", 640),
        device=config.get("device", "cpu"),
        show=config.get("show", True),
        roi_check_mode=config.get("roi_check_mode", "center"),
        monitored_areas=config.get("monitored_areas", None)
    )

    detector.run()
