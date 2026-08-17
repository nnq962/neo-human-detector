"""Kiểm thử lựa chọn pipeline GStreamer của RTSP reader."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np

from src.media_sources.readers import rtsp as rtsp_module
from src.media_sources.readers.rtsp import RtspReader


class _FakeCapture:
    """Capture giả dùng để mô phỏng quá trình warm-up pipeline."""

    def __init__(self, produces_frame: bool):
        """Khởi tạo capture giả có hoặc không tạo được frame."""
        self._produces_frame = produces_frame
        self.released = False
        self.properties: list[tuple[int, float]] = []

    # ─────────────────────────────────────────────────────────────────────────

    def isOpened(self) -> bool:
        """Báo capture đã mở để kiểm thử tiếp tục tới bước warm-up."""
        return True

    # ─────────────────────────────────────────────────────────────────────────

    def read(self):
        """Trả một frame giả nếu pipeline được cấu hình thành công."""
        if self._produces_frame:
            return True, np.zeros((2, 2, 3), dtype=np.uint8)
        return False, None

    # ─────────────────────────────────────────────────────────────────────────

    def set(self, prop: int, value: float) -> bool:
        """Ghi nhận thuộc tính OpenCV được thiết lập."""
        self.properties.append((prop, value))
        return True

    # ─────────────────────────────────────────────────────────────────────────

    def release(self) -> None:
        """Đánh dấu capture đã được giải phóng."""
        self.released = True


# ─────────────────────────────────────────────────────────────────────────────
def test_jetson_pipeline_uses_hardware_decoder() -> None:
    """Pipeline Jetson phải decode bằng NVDEC và trả frame BGR cho OpenCV."""
    reader = RtspReader("rtsp://camera")

    pipeline = reader._build_gstreamer_pipeline(
        "rtsp://camera",
        "h265",
        jetson_accelerated=True,
    )

    assert "rtph265depay ! h265parse ! nvv4l2decoder" in pipeline
    assert "nvvidconv ! video/x-raw,format=BGRx" in pipeline
    assert "video/x-raw,format=BGR ! appsink" in pipeline
    assert "avdec_h265" not in pipeline


# ─────────────────────────────────────────────────────────────────────────────
def test_software_pipeline_keeps_cpu_decoder() -> None:
    """Pipeline thường phải tiếp tục sử dụng software decoder hiện có."""
    reader = RtspReader("rtsp://camera")

    pipeline = reader._build_gstreamer_pipeline("rtsp://camera", "h264")

    assert "rtph264depay ! h264parse ! avdec_h264" in pipeline
    assert "nvv4l2decoder" not in pipeline


# ─────────────────────────────────────────────────────────────────────────────
def test_jetson_override_takes_priority_over_auto_detection() -> None:
    """Giá trị cấu hình tường minh phải ghi đè kết quả nhận diện thiết bị."""
    with patch.object(RtspReader, "_is_jetson", return_value=True):
        assert not RtspReader(
            "rtsp://camera",
            use_jetson_acceleration=False,
        )._should_use_jetson_acceleration()

    with patch.object(RtspReader, "_is_jetson", return_value=False):
        assert RtspReader(
            "rtsp://camera",
            use_jetson_acceleration=True,
        )._should_use_jetson_acceleration()


# ─────────────────────────────────────────────────────────────────────────────
def test_auto_detection_rejects_non_linux_platform() -> None:
    """Nhận diện tự động không được coi macOS hoặc Windows là Jetson."""
    with patch.object(
        rtsp_module.platform,
        "system",
        return_value="Darwin",
    ):
        with patch.object(
            rtsp_module.platform,
            "machine",
            return_value="arm64",
        ):
            assert not RtspReader._is_jetson()


# ─────────────────────────────────────────────────────────────────────────────
def test_auto_detection_accepts_l4t_marker() -> None:
    """Nhận diện tự động phải chấp nhận marker L4T trên Linux ARM64."""
    with patch.object(
        rtsp_module.platform,
        "system",
        return_value="Linux",
    ):
        with patch.object(
            rtsp_module.platform,
            "machine",
            return_value="aarch64",
        ):
            with patch.object(
                rtsp_module.Path,
                "is_file",
                return_value=True,
            ):
                assert RtspReader._is_jetson()


# ─────────────────────────────────────────────────────────────────────────────
def test_hardware_failure_falls_back_to_software_gstreamer(monkeypatch) -> None:
    """Reader phải thử software decoder sau khi cả hai pipeline NVDEC thất bại."""
    opened_pipelines: list[str] = []
    captures: list[_FakeCapture] = []

    def _fake_open_capture(src, backend, open_timeout_ms, read_timeout_ms):
        """Tạo capture thành công riêng cho pipeline software H.264."""
        opened_pipelines.append(src)
        cap = _FakeCapture("avdec_h264" in src and "nvv4l2decoder" not in src)
        captures.append(cap)
        return cap

    monkeypatch.setattr(rtsp_module, "open_capture", _fake_open_capture)
    reader = RtspReader("rtsp://camera")
    reader._jetson_acceleration_enabled = True

    cap, backend = reader._open_gstreamer("rtsp://camera")

    assert cap is captures[-1]
    assert backend == "GStreamer/software/h264"
    assert len(opened_pipelines) == 3
    assert all("nvv4l2decoder" in item for item in opened_pipelines[:2])
    assert "avdec_h264" in opened_pipelines[2]
    assert captures[0].released
    assert captures[1].released


# ─────────────────────────────────────────────────────────────────────────────
def test_mask_url_for_log_hides_rtsp_password() -> None:
    """URL log phải giữ địa chỉ stream nhưng không để lộ mật khẩu."""
    url = "rtsp://admin:secret%40value@10.70.22.210:554/Streaming/channels/101"

    assert RtspReader._mask_url_for_log(url) == (
        "rtsp://admin:***@10.70.22.210:554/Streaming/channels/101"
    )
