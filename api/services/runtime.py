from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Optional

from api.models.runtime import (
    ALLOWED_RUNTIME_BATCH_SIZES,
    RuntimeCommandRequest,
    RuntimeSettings,
    RuntimeSettingsUpdate,
)
from api.models.camera import Zone as CameraZone
from api.services import config_store
from src.app import Runtime, build_runtime_config
from src.detection.model_registry import resolve_model_artifact
from utils import LOGGER, load_config


DEFAULT_CONFIG_PATH = "configs/default.yaml"
STOP_JOIN_TIMEOUT_SECONDS = 10.0


def _now() -> datetime:
    """Trả thời điểm UTC hiện tại."""
    return datetime.now(timezone.utc)


def _isoformat(value: Optional[datetime]) -> Optional[str]:
    """Chuyển thời điểm thành chuỗi ISO nếu có giá trị."""
    return value.isoformat() if value is not None else None


# ─────────────────────────────────────────────────────────────────────────────
def _model_dump(model, **kwargs) -> dict:
    """Chuyển Pydantic model thành dictionary."""
    return model.model_dump(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
def _normalize_runtime_settings(value: dict | None) -> dict:
    """Chuẩn hóa section runtime trong cấu hình ứng dụng."""
    return RuntimeSettings(**(value or {})).model_dump()


# ─────────────────────────────────────────────────────────────────────────────
def _validate_runtime_settings(settings: dict, app_config: dict) -> None:
    """Kiểm tra camera và model tương thích với cấu hình runtime."""
    camera_ids = settings["camera_ids"]
    batch_size = len(camera_ids)

    if batch_size == 0:
        if settings["auto_start"]:
            raise ValueError("Cần chọn camera trước khi bật tự động khởi động.")
        return

    if batch_size not in ALLOWED_RUNTIME_BATCH_SIZES:
        raise ValueError("Runtime chỉ hỗ trợ batch 1, 2 hoặc 4 camera.")

    cameras = {
        str(camera.get("id")): camera
        for camera in app_config.get("cameras") or []
        if isinstance(camera, dict) and camera.get("id")
    }
    missing_ids = [camera_id for camera_id in camera_ids if camera_id not in cameras]
    if missing_ids:
        raise ValueError(f"Camera runtime không tồn tại: {', '.join(missing_ids)}.")

    disabled_ids = [
        camera_id
        for camera_id in camera_ids
        if not cameras[camera_id].get("enabled", True)
    ]
    if disabled_ids:
        raise ValueError(f"Camera runtime đang bị tắt: {', '.join(disabled_ids)}.")

    invalid_zones: list[str] = []
    for camera_id in camera_ids:
        for index, zone in enumerate(cameras[camera_id].get("zones") or []):
            try:
                CameraZone.model_validate(zone)
            except (TypeError, ValueError):
                zone_name = (
                    zone.get("name")
                    if isinstance(zone, dict)
                    else None
                )
                invalid_zones.append(
                    f"{camera_id}/{zone_name or f'zone-{index + 1}'}"
                )
    if invalid_zones:
        raise ValueError(
            "Zone runtime không hợp lệ: " + ", ".join(invalid_zones) + "."
        )

    model_id = (app_config.get("detection") or {}).get("model_id")
    artifact = resolve_model_artifact(model_id)
    if isinstance(artifact.batch_size, int) and artifact.batch_size != batch_size:
        raise ValueError(
            f"Model {artifact.id} chỉ hỗ trợ batch {artifact.batch_size}, "
            f"không hỗ trợ batch {batch_size}."
        )


# ─────────────────────────────────────────────────────────────────────────────
def get_runtime_config() -> dict:
    """Đọc cấu hình runtime và trả thêm batch size được suy ra."""
    config = config_store.get_config_data()
    settings = _normalize_runtime_settings(config.get("runtime"))
    return {**settings, "batch_size": len(settings["camera_ids"])}


# ─────────────────────────────────────────────────────────────────────────────
def update_runtime_config(update: RuntimeSettingsUpdate) -> dict:
    """Cập nhật một phần cấu hình runtime và lưu xuống YAML."""
    update_data = _model_dump(update, exclude_none=True, exclude_unset=True)
    if not update_data:
        return get_runtime_config()

    def mutate(config: dict) -> dict:
        """Áp dụng và kiểm tra cấu hình runtime mới."""
        current = _normalize_runtime_settings(config.get("runtime"))
        settings = _normalize_runtime_settings({**current, **update_data})
        _validate_runtime_settings(settings, config)
        config["runtime"] = settings
        return {**settings, "batch_size": len(settings["camera_ids"])}

    return config_store.update_config_data(mutate)


# ─────────────────────────────────────────────────────────────────────────────
def replace_runtime_config(settings: RuntimeSettings) -> dict:
    """Thay thế toàn bộ cấu hình runtime và lưu xuống YAML."""
    normalized = _normalize_runtime_settings(_model_dump(settings))

    def mutate(config: dict) -> dict:
        """Kiểm tra và ghi section runtime mới."""
        _validate_runtime_settings(normalized, config)
        config["runtime"] = normalized
        return {**normalized, "batch_size": len(normalized["camera_ids"])}

    return config_store.update_config_data(mutate)


# ─────────────────────────────────────────────────────────────────────────────
def _validate_runtime_start_config(config_path: str) -> None:
    """Kiểm tra cấu hình runtime đầy đủ trước khi tạo background thread."""
    app_config = load_config(config_path)
    settings = _normalize_runtime_settings(app_config.get("runtime"))
    if not settings["camera_ids"]:
        raise ValueError("Cần chọn camera trước khi khởi động runtime.")
    _validate_runtime_settings(settings, app_config)


# ─────────────────────────────────────────────────────────────────────────────
class RuntimeManager:
    def __init__(self) -> None:
        """Khởi tạo bộ quản lý vòng đời runtime."""
        self._lock = threading.RLock()
        self._runtime: Optional[Runtime] = None
        self._thread: Optional[threading.Thread] = None
        self._state = "stopped"
        self._config_path: Optional[str] = None
        self._preview: Optional[bool] = None
        self._started_at: Optional[datetime] = None
        self._stopped_at: Optional[datetime] = None
        self._last_error: Optional[str] = None

    # ─────────────────────────────────────────────────────────────────────────
    def status(self) -> dict:
        """Trả snapshot trạng thái runtime hiện tại."""
        with self._lock:
            return self._status_unlocked()

    # ─────────────────────────────────────────────────────────────────────────
    def start(self, command: Optional[RuntimeCommandRequest] = None) -> dict:
        """Khởi động runtime bằng cấu hình đã lưu."""
        command = command or RuntimeCommandRequest()
        config_path = command.config_path or DEFAULT_CONFIG_PATH
        preview = command.preview if command.preview is not None else False

        from api.services.manual_robot_task import (
            manual_robot_task_service,
            robot_uart_operation_lock,
        )
        from api.services.robot_heartbeat import robot_heartbeat_service
        from api.services.robot_move import robot_move_registry

        with robot_uart_operation_lock:
            with self._lock:
                if self._thread_alive_unlocked():
                    raise ValueError("Runtime is already running.")

                if manual_robot_task_service.has_active_tasks():
                    raise ValueError(
                        "Runtime cannot start while a manual robot task is active."
                    )
                if robot_move_registry.has_any_active_move(
                    robot_heartbeat_service.state_store
                ):
                    raise ValueError(
                        "Runtime cannot start while a manual robot move is active."
                    )

                from uart_v2.uart_manager import uart_manager_v2
                _validate_runtime_start_config(config_path)
                runtime_config = build_runtime_config(config_path, show=preview)
                runtime = Runtime(
                    runtime_config,
                    robot_uart=uart_manager_v2,
                    robot_state_store=robot_heartbeat_service.state_store,
                    register_robot_heartbeat_handler=False,
                )
                thread = threading.Thread(
                    target=self._run_runtime,
                    args=(runtime,),
                    name="app-runtime",
                    daemon=True,
                )

                self._runtime = runtime
                self._thread = thread
                self._state = "starting"
                self._config_path = config_path
                self._preview = preview
                self._started_at = _now()
                self._stopped_at = None
                self._last_error = None

                thread.start()
                return self._status_unlocked()

    # ─────────────────────────────────────────────────────────────────────────
    def stop(self) -> dict:
        """Dừng runtime và chờ luồng xử lý kết thúc."""
        with self._lock:
            runtime = self._runtime
            thread = self._thread

            if not self._thread_alive_unlocked():
                if runtime is not None:
                    runtime.stop()
                self._state = "stopped"
                if self._stopped_at is None:
                    self._stopped_at = _now()
                return self._status_unlocked()

            self._state = "stopping"

        if runtime is not None:
            runtime.request_stop()

        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=STOP_JOIN_TIMEOUT_SECONDS)

        with self._lock:
            if self._thread_alive_unlocked():
                self._state = "stopping"
            else:
                self._state = "stopped"
                self._stopped_at = _now()

            return self._status_unlocked()

    # ─────────────────────────────────────────────────────────────────────────
    def restart(self, command: Optional[RuntimeCommandRequest] = None) -> dict:
        """Dừng rồi khởi động lại runtime."""
        self.stop()
        return self.start(command)

    # ─────────────────────────────────────────────────────────────────────────
    def reload(self, command: Optional[RuntimeCommandRequest] = None) -> dict:
        """Nạp lại cấu hình và restart nếu runtime đang chạy."""
        command = command or RuntimeCommandRequest()

        with self._lock:
            should_restart = self._thread_alive_unlocked()
            config_path = command.config_path or self._config_path or DEFAULT_CONFIG_PATH
            preview = command.preview if command.preview is not None else self._preview

        next_command = RuntimeCommandRequest(config_path=config_path, preview=preview)

        if should_restart:
            return self.restart(next_command)

        _validate_runtime_start_config(config_path)
        build_runtime_config(config_path, show=preview)

        with self._lock:
            self._state = "stopped"
            self._config_path = config_path
            self._preview = preview
            self._last_error = None
            if self._stopped_at is None:
                self._stopped_at = _now()
            return self._status_unlocked()

    # ─────────────────────────────────────────────────────────────────────────
    def _run_runtime(self, runtime: Runtime) -> None:
        """Chạy runtime trong background thread và ghi nhận lỗi."""
        try:
            with self._lock:
                if self._runtime is runtime:
                    self._state = "running"

            runtime.run()
        except Exception as error:
            LOGGER.exception("Runtime failed: %s", error)
            try:
                runtime.stop()
            except Exception:
                LOGGER.exception("Failed to stop runtime after error.")

            with self._lock:
                if self._runtime is runtime:
                    self._state = "error"
                    self._last_error = str(error)
                    self._stopped_at = _now()
            return

        with self._lock:
            if self._runtime is runtime:
                self._state = "stopped"
                self._stopped_at = _now()

    # ─────────────────────────────────────────────────────────────────────────
    def _thread_alive_unlocked(self) -> bool:
        """Kiểm tra background thread khi caller đã giữ lock."""
        return self._thread is not None and self._thread.is_alive()

    # ─────────────────────────────────────────────────────────────────────────
    def _status_unlocked(self) -> dict:
        """Dựng trạng thái runtime khi caller đã giữ lock."""
        thread_alive = self._thread_alive_unlocked()
        runtime_running = bool(self._runtime and self._runtime.is_running)
        is_running = thread_alive and runtime_running
        uptime_seconds = None

        if self._started_at is not None and self._stopped_at is None:
            uptime_seconds = round((_now() - self._started_at).total_seconds(), 3)
        elif self._started_at is not None and self._stopped_at is not None:
            uptime_seconds = round((self._stopped_at - self._started_at).total_seconds(), 3)

        return {
            "state": self._state,
            "is_running": is_running,
            "thread_alive": thread_alive,
            "config_path": self._config_path,
            "preview": self._preview,
            "started_at": _isoformat(self._started_at),
            "stopped_at": _isoformat(self._stopped_at),
            "uptime_seconds": uptime_seconds,
            "batch_size": len(self._runtime.cameras) if self._runtime else 0,
            "cameras": self._camera_statuses_unlocked(),
            "performance": (
                self._runtime.get_performance_metrics()
                if self._runtime is not None
                else {"yolo": None, "reid": None}
            ),
            "last_error": self._last_error,
        }

    # ─────────────────────────────────────────────────────────────────────────
    def _camera_statuses_unlocked(self) -> list[dict]:
        """Dựng trạng thái từng camera của phiên runtime hiện tại."""
        if self._runtime is None:
            return []

        camera_fps = getattr(self._runtime, "_camera_fps", {}) or {}
        cameras = []

        for camera in self._runtime.cameras:
            zone_states = {
                zone.name: getattr(zone.state, "value", str(zone.state))
                for zone in camera.zones
            }
            fps = camera_fps.get(camera.id)
            cameras.append({
                "id": camera.id,
                "name": camera.name,
                "source": camera.source,
                "zones": len(camera.zones),
                "fps": round(float(fps), 3) if fps is not None else None,
                "zone_states": zone_states,
            })

        return cameras


runtime_manager = RuntimeManager()


def get_runtime_status() -> dict:
    """Trả trạng thái runtime hiện tại."""
    return runtime_manager.status()


# ─────────────────────────────────────────────────────────────────────────────
def get_runtime_tasks() -> dict:
    """Trả read-model task của phiên runtime hiện tại."""
    from src.robot_dispatch_v2 import runtime_task_activity_store

    return runtime_task_activity_store.snapshot()


def start_runtime(command: Optional[RuntimeCommandRequest] = None) -> dict:
    """Khởi động runtime bằng manager dùng chung."""
    return runtime_manager.start(command)


def stop_runtime() -> dict:
    """Dừng runtime bằng manager dùng chung."""
    return runtime_manager.stop()


def restart_runtime(command: Optional[RuntimeCommandRequest] = None) -> dict:
    """Khởi động lại runtime bằng manager dùng chung."""
    return runtime_manager.restart(command)


def reload_runtime(command: Optional[RuntimeCommandRequest] = None) -> dict:
    """Nạp lại runtime bằng manager dùng chung."""
    return runtime_manager.reload(command)
