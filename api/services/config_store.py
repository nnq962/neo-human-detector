import copy
from contextlib import contextmanager
import fcntl
import os
import tempfile
import threading
from typing import Callable, TypeVar

import cv2
import yaml
from utils import load_config

CONFIG_PATH = "configs/default.yaml"
_CONFIG_LOCK = threading.RLock()
_T = TypeVar("_T")


class FlowList(list):
    """Lớp hỗ trợ in mảng thành chuỗi inline [x, y] trong YAML."""


def flow_list_rep(dumper, data):
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)


yaml.add_representer(FlowList, flow_list_rep)


def _config_dir() -> str:
    return os.path.dirname(CONFIG_PATH) or "."


def _lock_path() -> str:
    return f"{CONFIG_PATH}.lock"


@contextmanager
def _locked_config_file(*, exclusive: bool):
    os.makedirs(_config_dir(), exist_ok=True)

    with _CONFIG_LOCK:
        with open(_lock_path(), "a", encoding="utf-8") as lock_file:
            lock_type = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            fcntl.flock(lock_file.fileno(), lock_type)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _prepare_config_for_yaml(config_dict: dict) -> dict:
    config_dict = copy.deepcopy(config_dict)
    config_dict.pop("source", None)

    # Ép kiểu điểm (points) thành mảng inline [x, y] thay vì list nhiều dòng.
    if "zones" in config_dict and config_dict["zones"] is not None:
        for zone in config_dict["zones"]:
            if "points" in zone:
                zone["points"] = [FlowList(point) for point in zone["points"]]

    if "cameras" in config_dict and config_dict["cameras"] is not None:
        for camera in config_dict["cameras"]:
            if "zones" in camera and camera["zones"] is not None:
                for zone in camera["zones"]:
                    if "points" in zone:
                        zone["points"] = [FlowList(point) for point in zone["points"]]

    return config_dict


def _read_config_data_unlocked() -> dict:
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError("Configuration file not found.")

    return load_config(CONFIG_PATH)


def _fsync_config_dir() -> None:
    try:
        dir_fd = os.open(_config_dir(), os.O_DIRECTORY)
    except OSError:
        return

    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _write_config_data_unlocked(config_dict: dict) -> None:
    config_dict = _prepare_config_for_yaml(config_dict)
    directory = _config_dir()
    basename = os.path.basename(CONFIG_PATH)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{basename}.",
        suffix=".tmp",
        dir=directory,
        text=True,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.dump(
                config_dict,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, CONFIG_PATH)
        _fsync_config_dir()
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def _notify_config_saved(config_dict: dict) -> None:
    # Bắn tín hiệu hot-reload cho các tham số an toàn, không cập nhật nóng camera/zones.
    try:
        from api.services import detector as detector_service

        detector_service.update_dynamic_params(config_dict)
    except Exception as e:
        import logging

        logging.warning(f"Could not trigger hot-reload: {e}")


def get_config_data() -> dict:
    with _locked_config_file(exclusive=False):
        return _read_config_data_unlocked()


def save_config_data(config_dict: dict) -> None:
    config_dict = copy.deepcopy(config_dict)

    with _locked_config_file(exclusive=True):
        _write_config_data_unlocked(config_dict)

    _notify_config_saved(config_dict)


def update_config_data(mutator: Callable[[dict], _T]) -> _T:
    with _locked_config_file(exclusive=True):
        config = _read_config_data_unlocked()
        result = mutator(config)
        _write_config_data_unlocked(config)

    _notify_config_saved(config)
    return result


def get_snapshot_image() -> bytes:
    config = get_config_data()
    cameras = config.get("cameras") or []
    stream = cameras[0].get("stream") if cameras else None
    rtsp_url = stream.get("source") if isinstance(stream, dict) else None

    if not rtsp_url:
        raise ValueError("Không tìm thấy RTSP URL trong config.")

    cap = cv2.VideoCapture(rtsp_url)
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError("Không thể kết nối đến Camera.")

    success, buffer = cv2.imencode(".jpg", frame)
    if not success:
        raise RuntimeError("Lỗi mã hóa ảnh JPEG.")

    return buffer.tobytes()
