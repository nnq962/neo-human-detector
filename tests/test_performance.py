"""Kiểm thử thống kê thời gian suy luận model."""

import pytest

from src.performance import ModelInferenceMetrics


# ─────────────────────────────────────────────────────────────────────────────
def test_metrics_returns_recent_window_statistics() -> None:
    """Kiểm tra snapshot chỉ dùng các mẫu trong cửa sổ gần nhất."""
    metrics = ModelInferenceMetrics(window_size=3)
    for value in (10.0, 20.0, 40.0, 80.0):
        metrics.record(value)

    assert metrics.snapshot() == {
        "last_ms": 80.0,
        "average_ms": 46.667,
        "min_ms": 20.0,
        "max_ms": 80.0,
        "sample_count": 3,
    }


# ─────────────────────────────────────────────────────────────────────────────
def test_metrics_rejects_invalid_window_size() -> None:
    """Kiểm tra cửa sổ không hợp lệ bị từ chối khi khởi tạo."""
    with pytest.raises(ValueError, match="window_size"):
        ModelInferenceMetrics(window_size=0)
