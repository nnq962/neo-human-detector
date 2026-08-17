"""Kiểm thử các tiện ích dùng chung cho media source."""

from __future__ import annotations

from src.media_sources import utils


# ─────────────────────────────────────────────────────────────────────────────
def test_open_capture_omits_timeout_params_for_gstreamer(monkeypatch) -> None:
    """GStreamer phải được mở không kèm timeout property của OpenCV."""
    calls: list[tuple[object, ...]] = []

    def _fake_video_capture(*args):
        """Ghi nhận đối số VideoCapture để kiểm tra overload được gọi."""
        calls.append(args)
        return object()

    monkeypatch.setattr(utils.cv2, "VideoCapture", _fake_video_capture)

    capture = utils.open_capture(
        "pipeline ! appsink",
        utils.cv2.CAP_GSTREAMER,
        open_timeout_ms=5000,
        read_timeout_ms=500,
    )

    assert capture is not None
    assert calls == [("pipeline ! appsink", utils.cv2.CAP_GSTREAMER)]
