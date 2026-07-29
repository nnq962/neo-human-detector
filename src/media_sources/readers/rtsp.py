from __future__ import annotations

import platform
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from utils import LOGGER

from src.media_sources.models import SourceMeta, SourceType
from src.media_sources.readers.base import BaseReader
from src.media_sources.utils import ensure_bgr, open_capture

# ─────────────────────────────────────────────────────────────────────────────


class RtspReader(BaseReader):
    """Đọc frame từ MỘT RTSP/RTMP stream với GStreamer/FFMPEG backend và auto-reconnect.

    Reconnect nằm bên trong `read()`: khi đọc thất bại, reader tự thử lại (exponential
    backoff) cho tới khi có frame hoặc bị `close()`. Thread điều phối ở StreamBatchReader
    chỉ việc gọi `read()` lặp lại; `close()` set stop-event để `read()` đang reconnect thoát ra.
    """

    source_type = SourceType.RTSP
    is_stream = True

    # Chỉ cảnh báo "OpenCV không có GStreamer" một lần cho cả tiến trình.
    _gstreamer_warning_emitted = False

    def __init__(
        self,
        source: str,
        *,
        reconnect: bool = True,
        reconnect_delay: float = 2.0,
        max_reconnect_attempts: int = 5,
        reconnect_forever: bool = True,
        use_gstreamer: bool = True,
        use_jetson_acceleration: bool | None = None,
        open_timeout_ms: int = 5000,
        read_timeout_ms: int = 5000,
    ):
        """Khởi tạo reader và cấu hình chính sách backend/reconnect cho stream."""
        super().__init__(source)
        self._reconnect = reconnect
        self._reconnect_delay = reconnect_delay
        self._max_reconnect_attempts = max_reconnect_attempts
        self._reconnect_forever = reconnect_forever
        self._use_gstreamer = use_gstreamer
        self._use_jetson_acceleration = use_jetson_acceleration
        self._jetson_acceleration_enabled = False
        self._open_timeout_ms = open_timeout_ms
        self._read_timeout_ms = read_timeout_ms
        self._cap: cv2.VideoCapture | None = None
        self._backend = "unknown"
        self._fps = 0.0
        self._stop_reconnect = threading.Event()

    # ─────────────────────────────────────────────────────────────────────────

    def open(self) -> "RtspReader":
        """Mở stream và ưu tiên backend GStreamer phù hợp với nền tảng."""
        url = self._source
        self._jetson_acceleration_enabled = self._should_use_jetson_acceleration()
        if (
            self._use_gstreamer
            and not self._opencv_has_gstreamer()
            and not RtspReader._gstreamer_warning_emitted
        ):
            LOGGER.warning(
                "use_gstreamer=True nhưng OpenCV không được build với GStreamer; "
                "tất cả stream sẽ dùng FFMPEG."
            )
            RtspReader._gstreamer_warning_emitted = True
        elif self._use_gstreamer and self._jetson_acceleration_enabled:
            reason = (
                "Phát hiện Jetson"
                if self._use_jetson_acceleration is None
                else "Đã bật tăng tốc Jetson"
            )
            LOGGER.info(
                "%s; ưu tiên GStreamer hardware decode bằng nvv4l2decoder.", reason
            )

        self._stop_reconnect.clear()
        LOGGER.info("Đang kết nối stream: %s", url)
        cap, backend = self._open_cap(url)
        self._cap = cap
        self._backend = backend
        self._fps = cap.get(cv2.CAP_PROP_FPS)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        res = f"{w}x{h}" if w > 0 and h > 0 else "unknown"
        fps_str = f"{self._fps:.1f} fps" if self._fps > 0 else "fps=unknown"
        LOGGER.info(
            "   → RTSP | %s | %s | backend=%s | is_stream=True", res, fps_str, backend
        )
        self._opened = True
        self._frame_index = 0
        return self

    # ─────────────────────────────────────────────────────────────────────────

    def read(self) -> tuple[np.ndarray, SourceMeta] | None:
        """Đọc frame kế tiếp và tạo metadata tương ứng."""
        self.ensure_open()
        frame = self._read_raw_frame()
        if frame is None:
            return None

        frame = ensure_bgr(frame)
        h, w = frame.shape[:2]
        meta = SourceMeta(
            name=self._source,
            source_type=SourceType.RTSP,
            frame_index=self._frame_index,
            resolution=(w, h),
            fps=self._fps,
            is_stream=True,
            timestamp=time.time(),
        )
        self._frame_index += 1
        return frame, meta

    # ─────────────────────────────────────────────────────────────────────────

    def request_stop(self) -> None:
        """Yêu cầu vòng đọc/reconnect dừng ở điểm an toàn gần nhất."""
        # Cho phép batch dừng vòng reconnect/đọc mà không release cap (thread tự release ở close()).
        self._stop_reconnect.set()

    # ─────────────────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Dừng reconnect và giải phóng capture hiện tại."""
        self._stop_reconnect.set()
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._opened = False

    # ─────────────────────────────────────────────────────────────────────────

    def _read_raw_frame(self) -> np.ndarray | None:
        """Đọc 1 frame thô; nếu thất bại thì áp dụng chính sách reconnect."""
        image = self._read_capture_once()
        if image is not None:
            return image

        if not self._reconnect:
            LOGGER.warning("RTSP mất kết nối, không reconnect: %s", self._source)
            return None

        return self._reconnect_and_read()

    # ─────────────────────────────────────────────────────────────────────────

    def _read_capture_once(self) -> np.ndarray | None:
        """Đọc 1 frame từ cap hiện tại, không reconnect."""
        if self._stop_reconnect.is_set() or self._cap is None:
            return None
        ok, image = self._cap.read()
        if ok and image is not None:
            return image
        return None

    # ─────────────────────────────────────────────────────────────────────────

    def _reconnect_and_read(self) -> np.ndarray | None:
        """Thử reconnect (exponential backoff) tới khi có frame, bị close, hoặc hết lượt."""
        attempt = 0
        while not self._stop_reconnect.is_set():
            attempt += 1
            if not self._reconnect_forever and attempt > self._max_reconnect_attempts:
                LOGGER.error(
                    "RTSP bỏ cuộc sau %d lần reconnect: %s",
                    self._max_reconnect_attempts,
                    self._source,
                )
                return None

            LOGGER.warning(
                "RTSP mất kết nối, thử lại lần %d: %s", attempt, self._source
            )
            if self._cap is not None:
                self._cap.release()
                self._cap = None

            # Backoff: tăng delay theo số lần thất bại, tối đa 60s
            delay = min(self._reconnect_delay * (2 ** min(attempt - 1, 5)), 60.0)
            if self._stop_reconnect.wait(timeout=delay):
                return None

            try:
                cap, backend = self._open_cap(self._source)
                self._cap = cap
                self._backend = backend
                self._fps = cap.get(cv2.CAP_PROP_FPS)
                LOGGER.info(
                    "RTSP reconnect thành công (lần %d, backend=%s): %s",
                    attempt,
                    backend,
                    self._source,
                )
                image = self._read_capture_once()
                if image is not None:
                    return image
            except Exception as exc:
                LOGGER.warning("RTSP reconnect lần %d thất bại: %s", attempt, exc)
                self._cap = None

        return None

    # ─────────────────────────────────────────────────────────────────────────

    def _open_cap(self, url: str) -> tuple[cv2.VideoCapture, str]:
        """Thử GStreamer trước, fallback sang FFMPEG. Trả về (cap, backend_label).

        RTMP bỏ qua GStreamer (rtspsrc không hỗ trợ rtmp://).
        """
        is_rtmp = url.lower().startswith("rtmp://")
        if self._use_gstreamer and not is_rtmp and self._opencv_has_gstreamer():
            result = self._open_gstreamer(url)
            if result is not None:
                return result
            LOGGER.warning(
                "GStreamer pipeline không thành công, fallback sang FFMPEG: %s", url
            )
        return self._open_ffmpeg(url)

    # ─────────────────────────────────────────────────────────────────────────

    def _open_ffmpeg(self, url: str) -> tuple[cv2.VideoCapture, str]:
        """Mở stream bằng backend FFMPEG làm phương án dự phòng."""
        cap = open_capture(
            url, cv2.CAP_FFMPEG, self._open_timeout_ms, self._read_timeout_ms
        )
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(f"Không kết nối được stream: {url}")
        return cap, "FFMPEG"

    # ─────────────────────────────────────────────────────────────────────────

    def _open_gstreamer(self, url: str) -> tuple[cv2.VideoCapture, str] | None:
        """Thử lần lượt h264 → h265; warm-up với timeout ngắn để detect codec nhanh.

        Dùng _WARMUP_TIMEOUT_MS thay vì None để tránh block vô hạn khi codec sai
        (GStreamer không có frame → pull_sample() block đến internal TCP timeout ~30s).
        Sau khi confirm frame thì apply production read_timeout_ms.
        """
        _WARMUP_TIMEOUT_MS = 500  # mỗi lần cap.read() chờ tối đa 500ms
        acceleration_modes = (
            (True, False) if self._jetson_acceleration_enabled else (False,)
        )
        for jetson_accelerated in acceleration_modes:
            for codec in ("h264", "h265"):
                cap = open_capture(
                    self._build_gstreamer_pipeline(
                        url,
                        codec,
                        jetson_accelerated=jetson_accelerated,
                    ),
                    cv2.CAP_GSTREAMER,
                    self._open_timeout_ms,
                    _WARMUP_TIMEOUT_MS,
                )
                if not cap.isOpened():
                    cap.release()
                    continue
                for _ in range(20):  # max 10s tổng (20 × 500ms)
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        if self._read_timeout_ms is not None and hasattr(
                            cv2, "CAP_PROP_READ_TIMEOUT_MSEC"
                        ):
                            cap.set(
                                cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                                float(self._read_timeout_ms),
                            )
                        backend = "Jetson-HW" if jetson_accelerated else "software"
                        return cap, f"GStreamer/{backend}/{codec}"
                cap.release()
            if jetson_accelerated:
                LOGGER.warning(
                    "Jetson hardware decode không thành công; "
                    "thử lại bằng GStreamer software decoder: %s",
                    url,
                )
        return None

    # ─────────────────────────────────────────────────────────────────────────

    def _build_gstreamer_pipeline(
        self,
        url: str,
        codec: str,
        *,
        jetson_accelerated: bool = False,
    ) -> str:
        """Dựng pipeline RTSP low-latency cho software hoặc Jetson hardware decode."""
        url_esc = url.replace('"', '\\"')
        depay_parse = (
            "rtph265depay ! h265parse"
            if codec == "h265"
            else "rtph264depay ! h264parse"
        )
        if jetson_accelerated:
            decode_convert = (
                f"{depay_parse} ! nvv4l2decoder ! nvvidconv "
                f"! video/x-raw,format=BGRx ! videoconvert "
                f"! video/x-raw,format=BGR"
            )
        else:
            decoder = "avdec_h265" if codec == "h265" else "avdec_h264"
            decode_convert = (
                f"{depay_parse} ! {decoder} ! videoconvert ! video/x-raw,format=BGR"
            )
        return (
            f'rtspsrc location="{url_esc}" protocols=tcp latency=0 '
            f"drop-on-latency=true do-retransmission=false "
            f"! {decode_convert} "
            f"! appsink sync=false async=false drop=true max-buffers=1"
        )

    # ─────────────────────────────────────────────────────────────────────────

    def _should_use_jetson_acceleration(self) -> bool:
        """Quyết định bật hardware decode theo override hoặc nhận diện Jetson."""
        if self._use_jetson_acceleration is not None:
            return self._use_jetson_acceleration
        return self._is_jetson()

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _is_jetson() -> bool:
        """Nhận diện NVIDIA Jetson qua kiến trúc và marker của L4T/device tree."""
        if platform.system() != "Linux":
            return False
        if platform.machine().lower() not in {"aarch64", "arm64"}:
            return False
        if Path("/etc/nv_tegra_release").is_file():
            return True

        for marker_path in (
            Path("/proc/device-tree/model"),
            Path("/proc/device-tree/compatible"),
        ):
            try:
                marker = marker_path.read_bytes().lower()
            except OSError:
                continue
            if b"nvidia" in marker and (b"jetson" in marker or b"tegra" in marker):
                return True
        return False

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _opencv_has_gstreamer() -> bool:
        """Kiểm tra OpenCV hiện tại có được build kèm backend GStreamer."""
        return any(
            "GStreamer:" in line and "YES" in line
            for line in cv2.getBuildInformation().splitlines()
        )
