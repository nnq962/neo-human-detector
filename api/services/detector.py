from threading import Thread
from typing import Optional

from api.models.detector import DetectorSettings, DetectorSettingsUpdate
from api.services import config_store
from src.app.runtime import Runtime, build_runtime_config
from src.detection.model_registry import validate_model_config
from utils import LOGGER


_runtime: Optional[Runtime] = None
_thread: Optional[Thread] = None


def _model_dump(model, **kwargs) -> dict:
    return model.model_dump(**kwargs)


def _normalize_detection_config(detection_cfg: dict) -> dict:
    return DetectorSettings(
        auto_start=False,
        detection={
            "task": detection_cfg.get("task", "pose"),
            "model_size": detection_cfg.get("model_size", "medium"),
            "batch_size": detection_cfg.get("batch_size", 1),
            "conf": detection_cfg.get("conf", 0.5),
            "tracker": detection_cfg.get("tracker", "bytetrack.yaml"),
            "verbose": detection_cfg.get("verbose", False),
        },
    ).detection.model_dump()


def _validate_detection_config(detection_cfg: dict) -> None:
    validate_model_config(
        model_size=detection_cfg.get("model_size", "medium"),
        task=detection_cfg.get("task", "pose"),
        batch_size=int(detection_cfg.get("batch_size", 1)),
    )


def get_detector_config() -> dict:
    cfg = config_store.get_config_data()
    return {
        "auto_start": cfg.get("auto_start", False),
        "detection": _normalize_detection_config(cfg.get("detection", {})),
    }


def update_detector_config(settings: DetectorSettingsUpdate) -> dict:
    update_data = _model_dump(settings, exclude_none=True, exclude_unset=True)

    if not update_data:
        return get_detector_config()

    def mutate(cfg: dict) -> None:
        if "auto_start" in update_data:
            cfg["auto_start"] = update_data["auto_start"]

        if "detection" in update_data:
            detection_cfg = cfg.setdefault("detection", {})
            detection_cfg.update(update_data["detection"])
            detection_cfg.update(_normalize_detection_config(detection_cfg))
            _validate_detection_config(detection_cfg)

    config_store.update_config_data(mutate)
    return get_detector_config()


def get_status() -> dict:
    if _runtime is None:
        return {"is_running": False, "cameras": []}

    detector = _runtime.detector
    detection = _runtime.config.detection
    return {
        "is_running": _runtime.is_running,
        "model_path": detector.model_path if detector else None,
        "task": detection.task,
        "conf": detection.conf,
        "batch_size": detection.batch_size,
        "verbose": detection.verbose,
        "cameras": [
            {
                "id": camera.id,
                "name": camera.name,
                "source": camera.source,
                "zones": len(camera.zones),
            }
            for camera in _runtime.cameras
        ],
    }


def get_latest_ws_payload():
    return None


def sync_uart_payload():
    return None


def update_dynamic_params(cfg: dict) -> None:
    # Runtime mới chưa có hot-reload an toàn cho detector/zone params.
    return None


def start() -> dict:
    global _runtime, _thread

    if _runtime and _runtime.is_running:
        return {"status": "already_running", "message": "Detector is already running."}

    cfg = build_runtime_config(config_store.CONFIG_PATH, show=False)
    _runtime = Runtime(cfg)
    _thread = Thread(target=_runtime.run, daemon=True)
    _thread.start()
    LOGGER.info("Detector runtime started.")

    return {"status": "started", "message": "Detector started successfully."}


def stop() -> dict:
    global _runtime, _thread

    if not _runtime or not _runtime.is_running:
        return {"status": "not_running", "message": "Detector is not running."}

    _runtime.stop()

    if _thread and _thread.is_alive():
        _thread.join(timeout=10)
        if _thread.is_alive():
            LOGGER.warning("Thread did not stop within timeout.")

    _runtime = None
    _thread = None

    LOGGER.info("Detector runtime stopped.")
    return {"status": "stopped", "message": "Detector stopped successfully."}
