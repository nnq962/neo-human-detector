"""
Runtime detect-only cho pipeline mới.

Mục tiêu của runtime này là chạy được bước YOLO detection trước, chưa nối:
- ByteTrack/tracking.
- ReID.
- Zone state machine.
- UART/WebSocket runtime.

Khi các module còn lại ổn định, file này có thể được mở rộng hoặc thay bằng
runtime đầy đủ hơn.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
from unidecode import unidecode

from src.camera import load_cameras_from_config
from src.detection import DetectionFrame, YoloDetector, build_yolo_detector_config
from src.outputs import draw_detection_overlay
from utils import LOGGER, load_config, restore_level_names


# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class DetectRuntimeConfig:
    """
    Cấu hình runtime detect-only.

    Các field YOLO chính được lấy từ `detector` trong YAML. `show/show_scale` chỉ
    phục vụ debug preview bằng OpenCV.
    """

    config_path: str = "configs/test.yaml"
    source: str = "configs/rtsp.streams"
    mode: str = "head"
    model_size: str = "nano"
    batch_size: int = 1
    conf: float = 0.5
    vid_stride: int = 1
    show: bool = False
    show_scale: float = 1.0
    verbose: bool = True
    max_frames: Optional[int] = None


# -----------------------------------------------------------------------------
class DetectOnlyRuntime:
    """
    Orchestrator detect-only.

    Class này giữ vòng đời chạy thử detection: chuẩn bị camera, chạy YOLO stream,
    log kết quả và cleanup tài nguyên khi dừng.
    """

    def __init__(self, config: DetectRuntimeConfig):
        self.config = config
        self.cameras = []
        self.detector: Optional[YoloDetector] = None
        self.is_running = False
        self._prev_times_by_camera: Dict[str, float] = {}

    def run(self) -> None:
        """Chạy vòng lặp detect-only tới khi hết stream, Ctrl+C hoặc max_frames."""
        import time

        self._prepare()
        self.is_running = True
        restore_level_names()

        LOGGER.info("Bắt đầu detect-only runtime.")

        try:
            assert self.detector is not None
            for result_index, detection_frame in enumerate(self.detector.predict_stream()):
                if not self.is_running:
                    break

                if self._should_stop_by_frame_limit(result_index):
                    LOGGER.info("Đã đạt max_frames=%s, dừng detect-only runtime.", self.config.max_frames)
                    break

                camera = self._camera_for_result(result_index)
                detection_frame.camera_id = camera.id
                fps = self._update_fps(camera.id, time.time())

                if self.config.verbose:
                    LOGGER.info(
                        "Camera: %s, Object: %s, FPS: %.1f",
                        camera.name,
                        detection_frame.count,
                        fps,
                    )

                if self.config.show:
                    self._show_detection_frame(camera, detection_frame, fps)

        except KeyboardInterrupt:
            LOGGER.info("Đã nhận Ctrl+C, dừng detect-only runtime.")
        finally:
            self.stop()

    def stop(self) -> None:
        """Dừng runtime và cleanup detector/OpenCV."""
        self.is_running = False

        if self.detector is not None:
            self.detector.close()
            self.detector = None

        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

        LOGGER.info("Detect-only runtime đã dừng.")

    def _prepare(self) -> None:
        """Load camera và khởi tạo YoloDetector."""
        cfg = load_config(self.config.config_path)
        self.cameras = load_cameras_from_config(
            cfg,
            parse_zones=False,
            warn_on_empty_zones=False,
        )

        if not self.cameras:
            raise RuntimeError("Không có camera enabled hợp lệ để chạy detect.")

        if len(self.cameras) != self.config.batch_size:
            raise ValueError(
                "Số camera enabled phải khớp batch_size của model: "
                f"cameras={len(self.cameras)}, batch_size={self.config.batch_size}."
            )

        self.detector = YoloDetector(
            build_yolo_detector_config(
                source=self.config.source,
                mode=self.config.mode,
                model_size=self.config.model_size,
                batch_size=self.config.batch_size,
                conf=self.config.conf,
                vid_stride=self.config.vid_stride,
                verbose=self.config.verbose,
            )
        )

        LOGGER.info("Config path: %s", self.config.config_path)
        LOGGER.info("Source: %s", self.config.source)
        LOGGER.info("Mode: %s", self.config.mode)
        LOGGER.info("Model size: %s", self.config.model_size)
        LOGGER.info("Batch size: %s", self.config.batch_size)
        LOGGER.info("Conf: %s", self.config.conf)
        LOGGER.info("Video stride: %s", self.config.vid_stride)
        LOGGER.info("Show: %s", self.config.show)
        LOGGER.info("Number of cameras: %s", len(self.cameras))

    def _camera_for_result(self, result_index: int) -> Any:
        """Map result đã flatten của Ultralytics về camera tương ứng."""
        return self.cameras[result_index % len(self.cameras)]

    def _show_detection_frame(
        self,
        camera: Any,
        detection_frame: DetectionFrame,
        fps: float,
    ) -> None:
        """Vẽ và hiển thị frame debug detect-only."""
        frame = _extract_raw_frame(detection_frame)
        if frame is None:
            return

        zone_names = [None] * detection_frame.count
        draw_detection_overlay(frame, detection_frame.detections, zone_names)
        _draw_fps_label(frame, camera.name, fps)

        if self.config.show_scale != 1.0:
            frame = _resize_frame(frame, self.config.show_scale)

        window_name = f"DetectOnly - {camera.name} ({camera.id})"
        cv2.imshow(window_name, frame)

        # Bấm q trong cửa sổ OpenCV để dừng nhanh khi chạy test thủ công.
        if cv2.waitKey(1) & 0xFF == ord("q"):
            self.is_running = False

    def _update_fps(self, camera_id: str, current_time: float) -> float:
        """Tính FPS riêng cho từng camera."""
        prev_time = self._prev_times_by_camera.get(camera_id)
        self._prev_times_by_camera[camera_id] = current_time

        if prev_time is None:
            return 0.0

        return 1.0 / max(current_time - prev_time, 1e-6)

    def _should_stop_by_frame_limit(self, result_index: int) -> bool:
        """Kiểm tra giới hạn số result để test script có thể tự kết thúc."""
        return self.config.max_frames is not None and result_index >= self.config.max_frames


# -----------------------------------------------------------------------------
def build_detect_runtime_config_from_file(
    config_path: str,
    *,
    max_frames: Optional[int] = None,
    show: Optional[bool] = None,
) -> DetectRuntimeConfig:
    """Đọc YAML và chuyển thành DetectRuntimeConfig."""
    cfg = load_config(config_path)
    detector_cfg = cfg.get("detector", {})
    streams_file = cfg.get("source", {}).get("streams_file", "configs/rtsp.streams")

    return DetectRuntimeConfig(
        config_path=config_path,
        source=str(streams_file),
        mode=detector_cfg.get("mode", "head"),
        model_size=detector_cfg.get("model_size", "nano"),
        batch_size=int(detector_cfg.get("batch_size", 1)),
        conf=float(detector_cfg.get("conf", 0.5)),
        vid_stride=int(detector_cfg.get("vid_stride", 1)),
        show=bool(detector_cfg.get("show", False)) if show is None else show,
        show_scale=float(detector_cfg.get("show_scale", 1.0)),
        verbose=bool(detector_cfg.get("verbose", True)),
        max_frames=max_frames,
    )


# -----------------------------------------------------------------------------
def run_detect_from_config(
    config_path: str = "configs/test.yaml",
    *,
    max_frames: Optional[int] = None,
    show: Optional[bool] = None,
) -> None:
    """Helper tiện cho script test: tạo runtime từ YAML rồi chạy detect-only."""
    runtime_config = build_detect_runtime_config_from_file(
        config_path,
        max_frames=max_frames,
        show=show,
    )
    DetectOnlyRuntime(runtime_config).run()


# -----------------------------------------------------------------------------
def _extract_raw_frame(detection_frame: DetectionFrame):
    """Lấy frame gốc từ raw YOLO result để vẽ debug."""
    raw_result = detection_frame.raw_result
    raw_frame = getattr(raw_result, "orig_img", None)

    if raw_frame is None:
        return None

    return raw_frame.copy()


# -----------------------------------------------------------------------------
def _draw_fps_label(frame, camera_name: str, fps: float) -> None:
    """Vẽ FPS lên góc trái frame."""
    label = f"{unidecode(camera_name)} FPS: {fps:.1f}"
    cv2.putText(
        frame,
        label,
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 255, 0),
        2,
    )


# -----------------------------------------------------------------------------
def _resize_frame(frame, scale: float):
    """Resize frame debug theo show_scale."""
    height, width = frame.shape[:2]
    new_dim = (int(width * scale), int(height * scale))

    return cv2.resize(frame, new_dim)


# -----------------------------------------------------------------------------
def resolve_project_config_path(path: str) -> str:
    """Chuẩn hóa đường dẫn config để script test chạy được từ nhiều cwd."""
    config_path = Path(path)
    if config_path.is_absolute():
        return str(config_path)

    return str(Path.cwd() / config_path)
