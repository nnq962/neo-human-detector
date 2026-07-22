from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Optional

from api.models.runtime import RuntimeCommandRequest
from src.app import Runtime, build_runtime_config
from utils import LOGGER


DEFAULT_CONFIG_PATH = "configs/default.yaml"
STOP_JOIN_TIMEOUT_SECONDS = 10.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


class RuntimeManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runtime: Optional[Runtime] = None
        self._thread: Optional[threading.Thread] = None
        self._state = "stopped"
        self._config_path: Optional[str] = None
        self._preview: Optional[bool] = None
        self._started_at: Optional[datetime] = None
        self._stopped_at: Optional[datetime] = None
        self._last_error: Optional[str] = None

    def status(self) -> dict:
        with self._lock:
            return self._status_unlocked()

    def start(self, command: Optional[RuntimeCommandRequest] = None) -> dict:
        command = command or RuntimeCommandRequest()
        config_path = command.config_path or DEFAULT_CONFIG_PATH
        preview = command.preview if command.preview is not None else False

        from api.services.manual_robot_task import (
            manual_robot_task_service,
            robot_uart_operation_lock,
        )

        with robot_uart_operation_lock:
            with self._lock:
                if self._thread_alive_unlocked():
                    raise ValueError("Runtime is already running.")

                if manual_robot_task_service.has_active_tasks():
                    raise ValueError(
                        "Runtime cannot start while a manual robot task is active."
                    )

                from uart_v2.uart_manager import uart_manager_v2
                from api.services.robot_heartbeat import robot_heartbeat_service

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

    def stop(self) -> dict:
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

    def restart(self, command: Optional[RuntimeCommandRequest] = None) -> dict:
        self.stop()
        return self.start(command)

    def reload(self, command: Optional[RuntimeCommandRequest] = None) -> dict:
        command = command or RuntimeCommandRequest()

        with self._lock:
            should_restart = self._thread_alive_unlocked()
            config_path = command.config_path or self._config_path or DEFAULT_CONFIG_PATH
            preview = command.preview if command.preview is not None else self._preview

        next_command = RuntimeCommandRequest(config_path=config_path, preview=preview)

        if should_restart:
            return self.restart(next_command)

        build_runtime_config(config_path, show=preview)

        with self._lock:
            self._state = "stopped"
            self._config_path = config_path
            self._preview = preview
            self._last_error = None
            if self._stopped_at is None:
                self._stopped_at = _now()
            return self._status_unlocked()

    def _run_runtime(self, runtime: Runtime) -> None:
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

    def _thread_alive_unlocked(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _status_unlocked(self) -> dict:
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
            "cameras": self._camera_statuses_unlocked(),
            "last_error": self._last_error,
        }

    def _camera_statuses_unlocked(self) -> list[dict]:
        if self._runtime is None:
            return []

        fps_tracker = getattr(self._runtime, "_fps_tracker", {}) or {}
        cameras = []

        for camera in self._runtime.cameras:
            zone_states = {
                zone.name: getattr(zone.state, "value", str(zone.state))
                for zone in camera.zones
            }
            fps = fps_tracker.get(camera.id)
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
    return runtime_manager.status()


# ─────────────────────────────────────────────────────────────────────────────
def get_runtime_tasks() -> dict:
    """Trả read-model task của phiên runtime hiện tại."""
    from src.robot_dispatch_v2 import runtime_task_activity_store

    return runtime_task_activity_store.snapshot()


def start_runtime(command: Optional[RuntimeCommandRequest] = None) -> dict:
    return runtime_manager.start(command)


def stop_runtime() -> dict:
    return runtime_manager.stop()


def restart_runtime(command: Optional[RuntimeCommandRequest] = None) -> dict:
    return runtime_manager.restart(command)


def reload_runtime(command: Optional[RuntimeCommandRequest] = None) -> dict:
    return runtime_manager.reload(command)
