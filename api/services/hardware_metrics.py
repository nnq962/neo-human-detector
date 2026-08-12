"""Thu thập snapshot tài nguyên phần cứng cho dashboard.

Module này không thêm dependency bên thứ ba. Nó ưu tiên dữ liệu sẵn có trên
Linux, hỗ trợ GPU NVIDIA qua ``nvidia-smi`` và GPU tích hợp của Jetson qua
sysfs. Các trường không xác định có giá trị ``None`` thay vì làm hỏng API.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import threading
from typing import Any


PROC_STAT_PATH = Path("/proc/stat")
PROC_MEMINFO_PATH = Path("/proc/meminfo")
PROC_CPUINFO_PATH = Path("/proc/cpuinfo")
DEVICE_TREE_MODEL_PATH = Path("/proc/device-tree/model")
JETSON_GPU_LOAD_PATHS = (
    Path("/sys/devices/gpu.0/load"),
    Path("/sys/devices/17000000.gpu/load"),
)


# ─────────────────────────────────────────────────────────────────────────────
def _read_text(path: Path) -> str | None:
    """Đọc nội dung text của tệp hệ thống và bỏ qua lỗi không khả dụng."""
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
def _read_first_line(path: Path) -> str | None:
    """Đọc dòng đầu tiên của một tệp hệ thống."""
    text = _read_text(path)
    return text.splitlines()[0].strip() if text else None


# ─────────────────────────────────────────────────────────────────────────────
def _parse_key_value_lines(text: str) -> dict[str, str]:
    """Chuyển các dòng dạng ``key: value`` thành dictionary."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            result[key.strip()] = value.strip()
    return result


# ─────────────────────────────────────────────────────────────────────────────
def _read_cpu_counters() -> dict[str, tuple[int, int]]:
    """Đọc tick tổng và rảnh cho CPU tổng cùng từng logical core."""
    text = _read_text(PROC_STAT_PATH)
    if not text:
        return {}

    counters: dict[str, tuple[int, int]] = {}
    for line in text.splitlines():
        fields = line.split()
        if not fields or (fields[0] != "cpu" and not fields[0].startswith("cpu")):
            continue
        if not fields[0][3:].isdigit() and fields[0] != "cpu":
            continue

        try:
            values = [int(value) for value in fields[1:]]
        except ValueError:
            continue
        if len(values) < 4:
            continue

        counters[fields[0]] = (
            sum(values),
            values[3] + (values[4] if len(values) > 4 else 0),
        )

    return counters


# ─────────────────────────────────────────────────────────────────────────────
def _cpu_usage_percent(
    current: tuple[int, int] | None,
    previous: tuple[int, int] | None,
) -> float | None:
    """Tính phần trăm CPU bận từ chênh lệch tick giữa hai mẫu."""
    if current is None or previous is None:
        return None

    total_delta = current[0] - previous[0]
    idle_delta = current[1] - previous[1]
    if total_delta <= 0:
        return None

    return round(max(0, min(100, (total_delta - idle_delta) * 100 / total_delta)), 2)


# ─────────────────────────────────────────────────────────────────────────────
def _cpu_model_name() -> str | None:
    """Lấy tên CPU từ ``/proc/cpuinfo`` khi kernel cung cấp thông tin này."""
    text = _read_text(PROC_CPUINFO_PATH)
    if not text:
        return None

    values = _parse_key_value_lines(text)
    return values.get("model name") or values.get("Hardware") or values.get("Processor")


# ─────────────────────────────────────────────────────────────────────────────
def _physical_cpu_cores() -> int | None:
    """Ước lượng số core vật lý từ cặp physical id và core id trên Linux."""
    text = _read_text(PROC_CPUINFO_PATH)
    if not text:
        return None

    cores: set[tuple[str, str]] = set()
    for section in text.split("\n\n"):
        values = _parse_key_value_lines(section)
        physical_id = values.get("physical id")
        core_id = values.get("core id")
        if physical_id is not None and core_id is not None:
            cores.add((physical_id, core_id))

    return len(cores) or None


# ─────────────────────────────────────────────────────────────────────────────
def _memory_metrics() -> dict[str, int | float | None]:
    """Tính dung lượng và phần trăm RAM sử dụng từ ``/proc/meminfo``."""
    text = _read_text(PROC_MEMINFO_PATH)
    if not text:
        return {"total_bytes": None, "available_bytes": None, "used_bytes": None, "usage_percent": None}

    values = _parse_key_value_lines(text)

    def kilobytes(name: str) -> int | None:
        """Đọc một giá trị kB trong MemInfo và đổi sang byte."""
        raw_value = values.get(name)
        if raw_value is None:
            return None
        try:
            return int(raw_value.split()[0]) * 1024
        except (IndexError, ValueError):
            return None

    total = kilobytes("MemTotal")
    available = kilobytes("MemAvailable")
    if available is None:
        free = kilobytes("MemFree") or 0
        buffers = kilobytes("Buffers") or 0
        cached = kilobytes("Cached") or 0
        available = free + buffers + cached if total is not None else None

    used = total - available if total is not None and available is not None else None
    usage_percent = round(used * 100 / total, 2) if used is not None and total else None
    return {
        "total_bytes": total,
        "available_bytes": available,
        "used_bytes": used,
        "usage_percent": usage_percent,
    }


# ─────────────────────────────────────────────────────────────────────────────
def _read_jetson_gpu_load() -> float | None:
    """Đọc GPU load Jetson từ sysfs, chuẩn hóa về phần trăm."""
    for path in JETSON_GPU_LOAD_PATHS:
        raw_value = _read_first_line(path)
        if raw_value is None:
            continue
        try:
            value = float(raw_value)
        except ValueError:
            continue
        return round(value / 10 if value > 100 else value, 2)
    return None


# ─────────────────────────────────────────────────────────────────────────────
def _nvidia_smi_gpus() -> list[dict[str, Any]]:
    """Lấy GPU NVIDIA rời bằng nvidia-smi, hoặc trả mảng rỗng khi không có."""
    command = [
        "nvidia-smi",
        "--query-gpu=index,name,utilization.gpu,memory.total,memory.used,temperature.gpu,power.draw",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return []

    if completed.returncode != 0:
        return []

    gpus = []
    for line in completed.stdout.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 7:
            continue
        try:
            index = int(fields[0])
        except ValueError:
            continue

        def number(value: str) -> float | None:
            """Chuyển số NVIDIA-SMI hoặc giá trị N/A về kiểu float an toàn."""
            try:
                return float(value)
            except ValueError:
                return None

        total_mib = number(fields[3])
        used_mib = number(fields[4])
        gpus.append({
            "index": index,
            "name": fields[1],
            "kind": "nvidia",
            "usage_percent": number(fields[2]),
            "memory_total_bytes": int(total_mib * 1024 * 1024) if total_mib is not None else None,
            "memory_used_bytes": int(used_mib * 1024 * 1024) if used_mib is not None else None,
            "temperature_celsius": number(fields[5]),
            "power_watts": number(fields[6]),
        })
    return gpus


# ─────────────────────────────────────────────────────────────────────────────
def _jetson_gpu() -> dict[str, Any] | None:
    """Trả GPU tích hợp Jetson khi phát hiện được sysfs Tegra."""
    usage_percent = _read_jetson_gpu_load()
    if usage_percent is None:
        return None

    model = _read_text(DEVICE_TREE_MODEL_PATH) or "NVIDIA Jetson integrated GPU"
    return {
        "index": 0,
        "name": model.replace("\x00", "").strip(),
        "kind": "jetson-integrated",
        "usage_percent": usage_percent,
        "memory_total_bytes": None,
        "memory_used_bytes": None,
        "temperature_celsius": None,
        "power_watts": None,
    }


# ─────────────────────────────────────────────────────────────────────────────
class HardwareMetricsService:
    """Lưu mẫu CPU trước đó và dựng snapshot phần cứng an toàn cho JSON."""

    def __init__(self) -> None:
        """Khởi tạo cache mẫu CPU rỗng."""
        self._lock = threading.Lock()
        self._previous_cpu_counters: dict[str, tuple[int, int]] = {}

    # ─────────────────────────────────────────────────────────────────────────
    def snapshot(self) -> dict[str, Any]:
        """Trả thông tin CPU, RAM và GPU tại thời điểm được gọi."""
        return {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "platform": self._platform_name(),
            "cpu": self._cpu_metrics(),
            "memory": _memory_metrics(),
            "gpus": self._gpu_metrics(),
        }

    # ─────────────────────────────────────────────────────────────────────────
    def _platform_name(self) -> str:
        """Nhận diện Jetson hoặc trả loại máy Linux/PC tổng quát."""
        model = _read_text(DEVICE_TREE_MODEL_PATH)
        if model and "jetson" in model.lower():
            return model.replace("\x00", "").strip()
        return os.uname().machine

    # ─────────────────────────────────────────────────────────────────────────
    def _cpu_metrics(self) -> dict[str, Any]:
        """Tạo snapshot CPU, dùng delta giữa hai lần gọi để tính usage."""
        current = _read_cpu_counters()
        with self._lock:
            previous = self._previous_cpu_counters
            self._previous_cpu_counters = current

        cores = [
            {
                "index": int(name[3:]),
                "usage_percent": _cpu_usage_percent(counters, previous.get(name)),
            }
            for name, counters in sorted(
                current.items(),
                key=lambda item: int(item[0][3:]) if item[0] != "cpu" else -1,
            )
            if name != "cpu"
        ]

        load_average = None
        try:
            load_average = [round(value, 2) for value in os.getloadavg()]
        except OSError:
            pass

        return {
            "name": _cpu_model_name(),
            "logical_cores": os.cpu_count(),
            "physical_cores": _physical_cpu_cores(),
            "usage_percent": _cpu_usage_percent(current.get("cpu"), previous.get("cpu")),
            "load_average": load_average,
            "cores": cores,
        }

    # ─────────────────────────────────────────────────────────────────────────
    def _gpu_metrics(self) -> list[dict[str, Any]]:
        """Ưu tiên GPU NVIDIA rời, sau đó thử GPU tích hợp của Jetson."""
        nvidia_gpus = _nvidia_smi_gpus()
        if nvidia_gpus:
            return nvidia_gpus

        jetson_gpu = _jetson_gpu()
        return [jetson_gpu] if jetson_gpu is not None else []


hardware_metrics_service = HardwareMetricsService()
