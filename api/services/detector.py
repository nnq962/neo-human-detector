from threading import Thread
from typing import Optional
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
        "batch_size": _detector.batch_size if _detector else None,
        "cameras": [
            {"id": camera.id, "name": camera.name, "source": camera.source, "zones": len(camera.zones)}
            for camera in _detector.cameras
        ] if _detector else [],
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

def update_zone(cameras_cfg: list) -> None:
    """Cập nhật riêng cấu hình Cameras/Zones."""
    global _detector
    if not _detector or not cameras_cfg:
        return
    try:
        from utils import load_cameras
        new_cameras = load_cameras({"cameras": cameras_cfg})
        _detector.update_cameras(new_cameras)
    except Exception as e:
        LOGGER.warning(f"Lỗi khi cập nhật nóng Cameras/Zones: {e}")


def update_dynamic_params(cfg: dict) -> None:
    """Cập nhật các tham số có thể thay đổi nóng (hot-reload) mà không cần restart detector."""
    global _detector
    if not _detector:
        return

    # Update các cờ logic trong detector (ví dụ: verbose)
    detector_cfg = cfg.get("detector", {})
    if "verbose" in detector_cfg:
        _detector.update_detector_params(verbose=detector_cfg["verbose"])

    zone_state_machine_cfg = cfg.get("zones_state_machine", {})
    zone_state_machine_params = {
        "confirm_enter_time": zone_state_machine_cfg.get("confirm_enter_time"),
        "confirm_exit_time": zone_state_machine_cfg.get("confirm_exit_time"),
        "pending_enter_miss_grace_time": zone_state_machine_cfg.get("pending_enter_miss_grace_time"),
    }
    if any(value is not None for value in zone_state_machine_params.values()):
        _detector.update_zone_state_machine_params(**zone_state_machine_params)


def start() -> dict:
    global _detector, _thread

    if _detector and _detector.is_running:
        return {"status": "already_running", "message": "Detector is already running."}

    try:
        cfg = config_service.get_config_data()
    except FileNotFoundError as e:
        raise RuntimeError(f"Config not found: {e}")

    from utils import load_cameras
    cameras = load_cameras(cfg)

    detector_opts = cfg.get("detector", {})
    detector_opts.update(cfg.get("zones_state_machine", {}))
    streams_file = cfg.get("source", {}).get("streams_file")
    if streams_file:
        detector_opts["source"] = streams_file

    _detector = Detector(
        cameras=cameras,
        **detector_opts
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
