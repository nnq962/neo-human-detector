"""Tiện ích thu thập thời gian suy luận model theo cửa sổ gần nhất."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import threading


DEFAULT_TIMING_WINDOW_SIZE = 120


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ModelInferenceMetrics:
    """Lưu thống kê thời gian suy luận thread-safe cho một model."""

    window_size: int = DEFAULT_TIMING_WINDOW_SIZE
    _samples_ms: deque[float] = field(default_factory=deque, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)

    def __post_init__(self) -> None:
        """Kiểm tra kích thước cửa sổ trước khi bắt đầu ghi nhận mẫu."""
        if self.window_size <= 0:
            raise ValueError("window_size phải lớn hơn 0.")
        self._samples_ms = deque(maxlen=self.window_size)

    # ─────────────────────────────────────────────────────────────────────────
    def record(self, elapsed_ms: float) -> None:
        """Ghi nhận một lần suy luận có thời lượng tính bằng mili giây."""
        with self._lock:
            self._samples_ms.append(max(0.0, float(elapsed_ms)))

    # ─────────────────────────────────────────────────────────────────────────
    def snapshot(self) -> dict | None:
        """Trả thống kê mẫu mới nhất và trung bình của cửa sổ hiện tại."""
        with self._lock:
            if not self._samples_ms:
                return None
            samples = tuple(self._samples_ms)

        return {
            "last_ms": round(samples[-1], 3),
            "average_ms": round(sum(samples) / len(samples), 3),
            "min_ms": round(min(samples), 3),
            "max_ms": round(max(samples), 3),
            "sample_count": len(samples),
        }
