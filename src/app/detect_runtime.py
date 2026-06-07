"""
Runtime detect + zone cho pipeline mới.

Runtime này nối các phần đã tách module: camera loader, YOLO detector, zone
geometry/state machine, WebSocket payload snapshot và visualization debug.
ReID vẫn được để lại cho bước refactor sau.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
from unidecode import unidecode

from src.camera import load_cameras_from_config
from src.app.runtime_state import RuntimeState
from src.detection import DetectionFrame, YoloDetector, YoloDetectorConfig
from src.outputs import build_detection_websocket_payload, draw_detection_overlay, draw_zones
from src.zones import ZoneStateMachine, assign_detections_to_zones
from utils import LOGGER, load_config, restore_level_names


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DetectRuntimeConfig:
    """
    Cấu hình runtime detect + zone.

    Các field YOLO chính được lấy từ `detector` trong YAML. `show/show_scale` chỉ
    phục vụ debug preview bằng OpenCV. Các field zone lấy từ `zones_state_machine`.
    """

    config_path: str = "configs/test.yaml"
    source: str = "configs/rtsp.streams"
    model_size: str = "nano"
    batch_size: int = 1
    conf: float = 0.5
    vid_stride: int = 1
    show: bool = False
    show_scale: float = 1.0
    verbose: bool = True
    use_tracking: bool = False
    tracker: str = "bytetrack.yaml"
    persist: bool = True
    zone_check_mode: str = "center"
    confirm_enter_time: float = 5.0
    confirm_exit_time: float = 5.0
    pending_enter_miss_grace_time: float = 1.5
    max_frames: Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
class DetectOnlyRuntime:
    """
    Orchestrator detect + zone.

    Tên class được giữ để script test hiện tại không phải đổi. Bên trong runtime
    đã có zone assignment, zone state machine và runtime state snapshot.
    """

    def __init__(self, config: DetectRuntimeConfig):
        self.config = config
        self.cameras = []
        self.detector: Optional[YoloDetector] = None
        self.zone_state_machine: Optional[ZoneStateMachine] = None
        self.state = RuntimeState()
        self.is_running = False
        self._prev_times_by_camera: Dict[str, float] = {}

    @property
    def latest_ws_payload(self) -> Dict[str, Any]:
        """Snapshot WebSocket payload mới nhất, tiện cho test/runtime khác đọc."""
        return self.state.get_websocket_snapshot()

    @property
    def latest_uart_payload(self) -> Dict[str, Any]:
        """Snapshot event zone mới nhất, giữ tên tương thích với detector cũ."""
        return self.state.get_uart_snapshot()

    def run(self) -> None:
        """Chạy vòng lặp detect + zone tới khi hết stream, Ctrl+C hoặc max_frames."""
        import time

        # 1. Chuẩn bị toàn bộ tài nguyên runtime: camera, zones, YOLO detector,
        #    zone state machine và reset snapshot state trước khi bắt đầu loop.
        self._prepare()
        self.is_running = True
        self.state.mark_running(True)
        restore_level_names()

        LOGGER.info(
            "Bắt đầu %s runtime.",
            "ByteTrack" if self.config.use_tracking else "detect-only",
        )

        try:
            assert self.detector is not None

            # 2. Chọn nguồn kết quả từ YOLO:
            #    - predict_stream(): detect thuần.
            #    - track_stream(): detect + ByteTrack id built-in của Ultralytics.
            stream = self._build_stream()
            for result_index, detection_frame in enumerate(stream):
                # 3. Các điều kiện dừng mềm để có thể stop từ bên ngoài hoặc test
                #    nhanh bằng max_frames mà không cần kill process.
                if not self.is_running:
                    break

                if self._should_stop_by_frame_limit(result_index):
                    LOGGER.info("Đã đạt max_frames=%s, dừng detect-only runtime.", self.config.max_frames)
                    break

                # 4. Ultralytics trả result theo thứ tự flatten của batch, nên cần
                #    map result_index ngược về camera tương ứng.
                camera = self._camera_for_result(result_index)
                zones = camera.zones
                detection_frame.camera_id = camera.id
                fps = self._update_fps(camera.id, time.time())

                # 5. Gắn từng detection vào zone, đồng thời đếm số người trong
                #    từng zone để state machine quyết định chuyển trạng thái.
                zone_names, zone_counts = assign_detections_to_zones(
                    detection_frame.detections,
                    zones,
                    self.config.zone_check_mode,
                )

                # 6. Cập nhật state machine. Nếu có detected/cleared event, payload
                #    này giữ format tương thích với UART pipeline cũ.
                zone_event_payload = self._update_zone_state(zones, zone_counts)

                # 7. Lưu snapshot mới nhất cho consumer bên ngoài đọc, ví dụ
                #    WebSocket preview hoặc UART sender trong bước refactor sau.
                self._update_runtime_payloads(
                    camera,
                    detection_frame,
                    zones,
                    zone_counts,
                    zone_event_payload,
                )

                if self.config.verbose:
                    LOGGER.info(
                        "Camera: %s, Object: %s, Tracked: %s, Zones: %s, FPS: %.1f",
                        camera.name,
                        detection_frame.count,
                        _count_tracked_detections(detection_frame),
                        _format_zone_counts(zone_counts),
                        fps,
                    )

                if self.config.show:
                    # 8. Preview debug: vẽ polygon zone, bbox/label và status bar.
                    self._show_detection_frame(camera, detection_frame, zone_names, fps)

        except KeyboardInterrupt:
            LOGGER.info("Đã nhận Ctrl+C, dừng detect-only runtime.")
        finally:
            # 9. Dù loop kết thúc vì lý do nào cũng cleanup detector/OpenCV.
            self.stop()

    def stop(self) -> None:
        """Dừng runtime và cleanup detector/OpenCV."""
        self.is_running = False
        self.state.mark_running(False)

        if self.detector is not None:
            self.detector.close()
            self.detector = None

        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

        LOGGER.info("Detect runtime đã dừng.")

    def _prepare(self) -> None:
        """Load camera, zone state machine và khởi tạo YoloDetector."""
        cfg = load_config(self.config.config_path)
        self.cameras = load_cameras_from_config(
            cfg,
            parse_zones=True,
            warn_on_empty_zones=True,
        )

        if not self.cameras:
            raise RuntimeError("Không có camera enabled hợp lệ để chạy detect.")

        if len(self.cameras) != self.config.batch_size:
            raise ValueError(
                "Số camera enabled phải khớp batch_size của model: "
                f"cameras={len(self.cameras)}, batch_size={self.config.batch_size}."
            )

        yolo_config = YoloDetectorConfig(
            source=self.config.source,
            model_size=self.config.model_size,
            batch_size=int(self.config.batch_size),
            conf=float(self.config.conf),
            vid_stride=int(self.config.vid_stride),
            tracker=self.config.tracker,
            persist=bool(self.config.persist),
            verbose=bool(self.config.verbose),
        )
        self.detector = YoloDetector(yolo_config)
        self.zone_state_machine = ZoneStateMachine(
            confirm_enter_time=float(self.config.confirm_enter_time),
            confirm_exit_time=float(self.config.confirm_exit_time),
            pending_enter_miss_grace_time=float(self.config.pending_enter_miss_grace_time),
        )
        self.state.reset()

        LOGGER.info("Config path: %s", self.config.config_path)
        LOGGER.info("Source: %s", self.config.source)
        LOGGER.info("Model size: %s", self.config.model_size)
        LOGGER.info("Batch size: %s", self.config.batch_size)
        LOGGER.info("Conf: %s", self.config.conf)
        LOGGER.info("Video stride: %s", self.config.vid_stride)
        LOGGER.info("Show: %s", self.config.show)
        LOGGER.info("Use tracking: %s", self.config.use_tracking)
        if self.config.use_tracking:
            LOGGER.info("Tracker: %s", self.config.tracker)
            LOGGER.info("Persist tracker: %s", self.config.persist)
        LOGGER.info("Zone check mode: %s", self.config.zone_check_mode)
        LOGGER.info("Confirm enter time: %s", self.config.confirm_enter_time)
        LOGGER.info("Confirm exit time: %s", self.config.confirm_exit_time)
        LOGGER.info(
            "Pending enter miss grace time: %s",
            self.config.pending_enter_miss_grace_time,
        )
        LOGGER.info("Number of cameras: %s", len(self.cameras))

    def _build_stream(self):
        """Chọn stream detect hoặc ByteTrack tùy cấu hình runtime."""
        assert self.detector is not None

        if self.config.use_tracking:
            return self.detector.track_stream()

        return self.detector.predict_stream()

    def _camera_for_result(self, result_index: int) -> Any:
        """Map result đã flatten của Ultralytics về camera tương ứng."""
        return self.cameras[result_index % len(self.cameras)]

    def _show_detection_frame(
        self,
        camera: Any,
        detection_frame: DetectionFrame,
        zone_names,
        fps: float,
    ) -> None:
        """Vẽ và hiển thị frame debug gồm zone + detection."""
        frame = _extract_raw_frame(detection_frame)
        if frame is None:
            return

        draw_zones(frame, camera.zones)
        draw_detection_overlay(frame, detection_frame.detections, zone_names)
        _draw_fps_label(frame, camera.name, fps, detection_frame.count)

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

    def _update_zone_state(self, zones, zone_counts: Dict[str, int]) -> Dict[str, Any]:
        """Cập nhật state machine và log event zone nếu có."""
        if self.zone_state_machine is None:
            return {"detected": [], "cleared": []}

        payload = self.zone_state_machine.update(zones, zone_counts)
        if payload["detected"] or payload["cleared"]:
            LOGGER.info("Zone event payload: %s", payload)

        return payload

    def _update_runtime_payloads(
        self,
        camera: Any,
        detection_frame: DetectionFrame,
        zones,
        zone_counts: Dict[str, int],
        zone_event_payload: Dict[str, Any],
    ) -> None:
        """Cập nhật snapshot WebSocket và UART-like zone event trong RuntimeState."""
        camera_payload = build_detection_websocket_payload(
            camera=camera,
            detection_frame=detection_frame,
            zones=zones,
            zone_counts=zone_counts,
        )
        self.state.update_camera_payload(camera.id, camera_payload)

        if zone_event_payload["detected"] or zone_event_payload["cleared"]:
            self.state.update_zone_event_payload(zone_event_payload)


# ─────────────────────────────────────────────────────────────────────────────
def build_detect_runtime_config_from_file(
    config_path: str,
    *,
    max_frames: Optional[int] = None,
    show: Optional[bool] = None,
    use_tracking: bool = False,
    tracker: str = "bytetrack.yaml",
    persist: bool = True,
) -> DetectRuntimeConfig:
    """Đọc YAML và chuyển thành DetectRuntimeConfig."""
    cfg = load_config(config_path)
    detector_cfg = cfg.get("detector", {})
    zone_cfg = cfg.get("zones_state_machine", {})
    streams_file = cfg.get("source", {}).get("streams_file", "configs/rtsp.streams")

    return DetectRuntimeConfig(
        config_path=config_path,
        source=str(streams_file),
        model_size=detector_cfg.get("model_size", "nano"),
        batch_size=int(detector_cfg.get("batch_size", 1)),
        conf=float(detector_cfg.get("conf", 0.5)),
        vid_stride=int(detector_cfg.get("vid_stride", 1)),
        show=bool(detector_cfg.get("show", False)) if show is None else show,
        show_scale=float(detector_cfg.get("show_scale", 1.0)),
        verbose=bool(detector_cfg.get("verbose", True)),
        use_tracking=use_tracking,
        tracker=tracker,
        persist=persist,
        zone_check_mode=zone_cfg.get("zone_check_mode", "center"),
        confirm_enter_time=float(zone_cfg.get("confirm_enter_time", 5.0)),
        confirm_exit_time=float(zone_cfg.get("confirm_exit_time", 5.0)),
        pending_enter_miss_grace_time=float(
            zone_cfg.get("pending_enter_miss_grace_time", 1.5)
        ),
        max_frames=max_frames,
    )


# ─────────────────────────────────────────────────────────────────────────────
def run_detect_from_config(
    config_path: str = "configs/test.yaml",
    *,
    max_frames: Optional[int] = None,
    show: Optional[bool] = None,
    use_tracking: bool = False,
    tracker: str = "bytetrack.yaml",
    persist: bool = True,
) -> None:
    """Helper tiện cho script test: tạo runtime từ YAML rồi chạy detect-only."""
    runtime_config = build_detect_runtime_config_from_file(
        config_path,
        max_frames=max_frames,
        show=show,
        use_tracking=use_tracking,
        tracker=tracker,
        persist=persist,
    )
    DetectOnlyRuntime(runtime_config).run()


# ─────────────────────────────────────────────────────────────────────────────
def _extract_raw_frame(detection_frame: DetectionFrame):
    """Lấy frame gốc từ raw YOLO result để vẽ debug."""
    raw_result = detection_frame.raw_result
    raw_frame = getattr(raw_result, "orig_img", None)

    if raw_frame is None:
        return None

    return raw_frame.copy()


# ─────────────────────────────────────────────────────────────────────────────
def _draw_fps_label(frame, camera_name: str, fps: float, detection_count: int) -> None:
    """Vẽ thanh trạng thái full-width ở đầu frame."""
    frame_height, frame_width = frame.shape[:2]
    draw_scale = _get_draw_scale(frame)
    font_scale = _scale_float(1.0, draw_scale)
    thickness = _scale_int(2, draw_scale)
    padding_x = _scale_int(14, draw_scale)
    padding_bottom = _scale_int(14, draw_scale)
    bar_height = max(_scale_int(52, draw_scale), int(frame_height * 0.045))
    label = (
        f"{_format_camera_label(camera_name)} - "
        f"{frame_width}x{frame_height} - "
        f"{int(round(fps))}fps - "
        f"{detection_count} {_person_label(detection_count)} detected"
    )

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (frame_width, bar_height), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

    cv2.putText(
        frame,
        label,
        (padding_x, min(bar_height - padding_bottom, _scale_int(36, draw_scale))),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _format_camera_label(camera_name: str) -> str:
    """Chuẩn hóa tên camera cho status bar."""
    normalized = unidecode(str(camera_name)).strip()
    return normalized.replace(" ", "_").upper() or "CAMERA"


# ─────────────────────────────────────────────────────────────────────────────
def _person_label(count: int) -> str:
    """Trả nhãn person/persons theo số lượng detection."""
    return "person" if count == 1 else "persons"


# ─────────────────────────────────────────────────────────────────────────────
def _get_draw_scale(frame) -> float:
    """Tính scale vẽ dựa trên chiều cao frame, lấy Full HD làm mốc 1.0."""
    frame_height = frame.shape[0]
    return max(0.65, min(frame_height / 1080, 2.4))


# ─────────────────────────────────────────────────────────────────────────────
def _scale_int(value: int, scale: float) -> int:
    """Scale một số nguyên dùng cho pixel/padding/thickness."""
    return max(1, int(round(value * scale)))


# ─────────────────────────────────────────────────────────────────────────────
def _scale_float(value: float, scale: float) -> float:
    """Scale một số thực dùng cho font scale."""
    return max(0.1, value * scale)


# ─────────────────────────────────────────────────────────────────────────────
def _resize_frame(frame, scale: float):
    """Resize frame debug theo show_scale."""
    height, width = frame.shape[:2]
    new_dim = (int(width * scale), int(height * scale))

    return cv2.resize(frame, new_dim)


# ─────────────────────────────────────────────────────────────────────────────
def _count_tracked_detections(detection_frame: DetectionFrame) -> int:
    """Đếm số detection đã được ByteTrack gán track_id."""
    return sum(1 for detection in detection_frame.detections if detection.track_id is not None)


# ─────────────────────────────────────────────────────────────────────────────
def _format_zone_counts(zone_counts: Dict[str, int]) -> str:
    """Format zone_counts ngắn gọn cho log runtime."""
    if not zone_counts:
        return "-"

    return ", ".join(f"{key}={count}" for key, count in zone_counts.items())


# ─────────────────────────────────────────────────────────────────────────────
def resolve_project_config_path(path: str) -> str:
    """Chuẩn hóa đường dẫn config để script test chạy được từ nhiều cwd."""
    config_path = Path(path)
    if config_path.is_absolute():
        return str(config_path)

    return str(Path.cwd() / config_path)
