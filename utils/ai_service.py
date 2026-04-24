"""
AI Service — Logic nội bộ điều khiển vòng đời AI Task.
Được sử dụng bởi api_routes.py để start / stop / restart detector.
"""

import threading
from utils.logger import LOGGER

# Lock chống spam gọi start/stop đồng thời
ai_lock = threading.Lock()


def do_start_ai(app_state):
    """Khởi động thread AI mới. Caller phải đảm bảo đã acquire ai_lock."""
    # Khởi tạo lại một đối tượng HumanDetector mới với config mới nhất
    from utils import load_config
    from human_detector import HumanDetector
    
    config = load_config("config.json")
    app_state.detector = HumanDetector(
        source=config.get("source", 0),
        conf=config.get("conf", 0.5),
        imgsz=config.get("imgsz", 640),
        device=config.get("device", "cpu"),
        show=config.get("show", False),
        roi_check_mode=config.get("roi_check_mode", "center"),
        monitored_areas=config.get("monitored_areas", None),
        display_scale=config.get("display_scale", 0.55),
        ws_queue=app_state.data_queue
    )
    detector = app_state.detector
    detector.is_running = True
    
    def run_ai():
        LOGGER.info("Khởi động AI từ API...")
        detector.run()
    
    app_state.ai_thread = threading.Thread(target=run_ai, daemon=True)
    app_state.ai_thread.start()


def do_stop_ai(app_state):
    """Dừng AI và chờ thread kết thúc. Caller phải đảm bảo đã acquire ai_lock.
    
    Returns:
        tuple: (success: bool, message: str)
    """
    detector = app_state.detector
    detector.stop()
    
    ai_thread = getattr(app_state, "ai_thread", None)
    if ai_thread and ai_thread.is_alive():
        ai_thread.join(timeout=10)
        if ai_thread.is_alive():
            LOGGER.warning("Thread AI chưa kết thúc sau 10s timeout.")
            return False, "AI stop requested but thread still running"
    
    app_state.ai_thread = None
    return True, "AI stopped and resources released"
