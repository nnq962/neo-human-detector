from threading import Thread
from typing import Optional
from src.detector import Detector, MODEL_PATHS
from api.models.detector import DetectorSettings, DetectorSettingsUpdate
from api.services import config_store
from utils import LOGGER

_detector: Optional[Detector] = None
_thread: Optional[Thread] = None


def _model_dump(model, **kwargs) -> dict:
    return model.model_dump(**kwargs)


def _normalize_detector_config(detector_cfg: dict) -> dict:
    return DetectorSettings(
        auto_start=False,
        detector={
            "model_size": detector_cfg.get("model_size", "nano"),
            "batch_size": detector_cfg.get("batch_size", 1),
            "conf": detector_cfg.get("conf", 0.5),
            "vid_stride": detector_cfg.get("vid_stride", 1),
            "verbose": detector_cfg.get("verbose", False),
        },
    ).detector.model_dump()


def _validate_detector_model_config(detector_cfg: dict) -> None:
    model_size = detector_cfg.get("model_size", "nano")
    batch_size = int(detector_cfg.get("batch_size", 1))

    if (model_size, batch_size) not in MODEL_PATHS:
        supported = ", ".join(
            f"{size}/batch{batch}" for size, batch in sorted(MODEL_PATHS)
        )
        raise ValueError(
            f"Unsupported model_size/batch_size: {model_size}/batch{batch_size}. "
            f"Supported: {supported}"
        )


def get_detector_config() -> dict:
    cfg = config_store.get_config_data()

    return {
        "auto_start": cfg.get("auto_start", False),
        "detector": _normalize_detector_config(cfg.get("detector", {})),
    }


def update_detector_config(settings: DetectorSettingsUpdate) -> dict:
    cfg = config_store.get_config_data()
    update_data = _model_dump(settings, exclude_none=True, exclude_unset=True)
    cfg.setdefault("detector", {}).pop("mode", None)

    if "auto_start" in update_data:
        cfg["auto_start"] = update_data["auto_start"]

    if "detector" in update_data:
        detector_cfg = cfg.setdefault("detector", {})
        detector_cfg.update(update_data["detector"])
        detector_cfg.update(_normalize_detector_config(detector_cfg))
        _validate_detector_model_config(detector_cfg)

    config_store.save_config_data(cfg)

    return get_detector_config()


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

def update_dynamic_params(cfg: dict) -> None:
    """Cập nhật các tham số có thể thay đổi nóng (hot-reload) mà không cần restart detector."""
    global _detector
    if not _detector:
        return

    detector_cfg = cfg.get("detector", {})
    zone_state_machine_cfg = cfg.get("zones_state_machine", {})
    detector_params = {
        "verbose": detector_cfg.get("verbose"),
        "zone_check_mode": zone_state_machine_cfg.get("zone_check_mode"),
    }
    if any(value is not None for value in detector_params.values()):
        _detector.update_detector_params(**detector_params)

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
        cfg = config_store.get_config_data()
    except FileNotFoundError as e:
        raise RuntimeError(f"Config not found: {e}")

    from src.camera import load_cameras_from_config

    cameras = load_cameras_from_config(cfg)

    detector_opts = dict(cfg.get("detector", {}))
    detector_opts.pop("mode", None)
    detector_opts.update(_normalize_detector_config(detector_opts))
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
