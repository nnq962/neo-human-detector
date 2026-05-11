from threading import Thread
from typing import Optional
from src.detector import Detector
from src.detector import Detector
from api.services import config as config_service
from utils import LOGGER

_detector: Optional[Detector] = None
_thread: Optional[Thread] = None


def get_status() -> dict:
    return {
        "is_running": _detector.is_running if _detector else False,
        "source": _detector.source if _detector else None,
        "model_path": _detector.model_path if _detector else None,
        "conf": _detector.conf if _detector else None,
        "vid_stride": _detector.vid_stride if _detector else None,
        "verbose": _detector.verbose if _detector else None,
    }

def get_latest_ws_payload():
    """Hàm trung gian để FastAPI có thể lấy dữ liệu websocket mới nhất từ Detector."""
    global _detector
    if _detector:
        return _detector.latest_ws_payload
    return None

def sync_uart_payload():
    """Gọi Detector gửi lại dữ liệu UART gần nhất."""
    global _detector
    if _detector:
        _detector.sync_uart()

def update_zone(zones_cfg: list) -> None:
    """Cập nhật riêng cấu hình Zones."""
    global _detector
    if not _detector or not zones_cfg:
        return
    try:
        from utils.load_zones import load_zones
        new_zones = load_zones({"zones": zones_cfg})
        _detector.update_zone(new_zones)
    except Exception as e:
        LOGGER.warning(f"Lỗi khi cập nhật nóng Zone: {e}")


def update_dynamic_params(cfg: dict) -> None:
    """Cập nhật các tham số có thể thay đổi nóng (hot-reload) mà không cần restart detector."""
    global _detector
    if not _detector:
        return

    # Update các cờ logic trong detector (ví dụ: verbose)
    detector_cfg = cfg.get("detector", {})
    if "verbose" in detector_cfg:
        _detector.update_detector_params(verbose=detector_cfg["verbose"])


def start() -> dict:
    global _detector, _thread

    if _detector and _detector.is_running:
        return {"status": "already_running", "message": "Detector is already running."}

    try:
        cfg = config_service.get_config_data()
    except FileNotFoundError as e:
        raise RuntimeError(f"Config not found: {e}")

    # Load zones từ config
    from utils.load_zones import load_zones
    zones = load_zones(cfg)

    _detector = Detector(
        zones=zones,
        **cfg.get("detector", {})
    )

    _thread = Thread(target=_detector.run, daemon=True)
    _thread.start()
    LOGGER.info("Detector started.")

    return {"status": "started", "message": "Detector started successfully."}


def stop() -> dict:
    global _detector, _thread

    if not _detector or not _detector.is_running:
        return {"status": "not_running", "message": "Detector is not running."}

    # 1. Signal dừng + cleanup resource trong detector
    _detector.stop()

    # 2. Chờ thread kết thúc hẳn (timeout 10s để tránh treo)
    if _thread and _thread.is_alive():
        _thread.join(timeout=10)
        if _thread.is_alive():
            LOGGER.warning("Thread did not stop within timeout.")

    # 3. Xóa reference để GC có thể thu hồi memory
    _detector = None
    _thread = None

    LOGGER.info("Detector stopped.")
    return {"status": "stopped", "message": "Detector stopped successfully."}