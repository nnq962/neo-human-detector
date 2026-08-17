"""Kiểm thử cache FPS realtime của runtime."""

import pytest

from src.app.datatypes import RuntimeConfig
from src.app.runtime import Runtime


# ─────────────────────────────────────────────────────────────────────────────
def test_runtime_stores_calculated_fps_separately_from_timestamp() -> None:
    """Kiểm tra API có thể đọc FPS thay vì timestamp nội bộ của frame trước."""
    runtime = Runtime(RuntimeConfig())

    assert runtime._update_fps("camera-1", 100.0) == 0.0
    assert runtime._update_fps("camera-1", 100.04) == pytest.approx(25.0)
    assert runtime._fps_tracker["camera-1"] == 100.04
    assert runtime._camera_fps["camera-1"] == pytest.approx(25.0)
