"""
Runtime detect + zone cho pipeline mới.

Runtime này nối các phần đã tách module: camera loader, YOLO detector, zone
geometry/state machine, WebSocket payload snapshot và visualization debug.
ReID vẫn được để lại cho bước refactor sau.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from unidecode import unidecode

import cv2

from src.camera import Camera, load_cameras_from_config
from src.app.runtime_state import RuntimeState
from src.detection import DetectionFrame, YoloDetector, YoloDetectorConfig
from src.outputs import (
    build_detection_websocket_payload,
    draw_detection_overlay,
    draw_fps_label,
    draw_zones,
    extract_raw_frame,
    resize_frame,
)
from src.reid import ReIdConfig, ReIdPipeline
from src.zones import (
    ZoneOccupancyManager,
    ZoneState,
    ZoneStateMachine,
    assign_detections_to_zones,
    build_zone_occupancy_snapshot,
) 
from utils import LOGGER, load_config, restore_level_names, LINE_CHAR


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DetectRuntimeConfig:
    """
    Cấu hình runtime detect + zone.

    Các field YOLO chính được lấy từ `detector` trong YAML. `show/show_scale` chỉ
    phục vụ debug preview bằng OpenCV. Các field zone lấy từ `zones_state_machine`.
    """

    config_path                  : str           = "configs/test.yaml"
    source                       : str           = "configs/rtsp.streams"
    model_size                   : str           = "nano"
    batch_size                   : int           = 1
    conf                         : float         = 0.5
    vid_stride                   : int           = 1
    show                         : bool          = False
    show_scale                   : float         = 1.0
    verbose                      : bool          = True
    use_tracking                 : bool          = False
    tracker                      : str           = "bytetrack.yaml"
    persist                      : bool          = True
    reid_config                  : ReIdConfig    = field(default_factory=ReIdConfig)
    zone_check_mode              : str           = "center"
    confirm_enter_time           : float         = 5.0
    confirm_exit_time            : float         = 5.0
    pending_enter_miss_grace_time: float         = 1.5
    max_frames                   : Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
class DetectOnlyRuntime:
    """
    Orchestrator detect + zone.

    Tên class được giữ để script test hiện tại không phải đổi. Bên trong runtime
    đã có zone assignment, zone state machine và runtime state snapshot.
    """

    def __init__(self, config: DetectRuntimeConfig):
        self.config = config
        self.cameras: list[Camera] = []
        self.detector: Optional[YoloDetector] = None
        self.zone_state_machine: Optional[ZoneStateMachine] = None
        self.zone_occupancy_manager = ZoneOccupancyManager()
        self.reid_pipeline: Optional[ReIdPipeline] = None
        self.state = RuntimeState()
        self.is_running = False
        self._prev_times_by_camera: Dict[str, float] = {}

    @property
    def latest_ws_payload(self) -> Dict[str, Any]:
        """Snapshot WebSocket payload mới nhất, tiện cho test/runtime khác đọc."""
        return self.state.get_websocket_snapshot()

    @property
    def latest_robot_requests(self) -> list:
        """Snapshot request robot mới nhất do occupancy layer phát sinh."""
        return self.state.get_robot_requests_snapshot()

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
            "Start %s runtime.",
            "ReID"
            if self.config.reid_config.enabled
            else "ByteTrack"
            if self.config.use_tracking
            else "detect-only",
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

                # 6. Cập nhật state machine trước ReID để biết zone nào đã thật sự
                #    OCCUPIED, tránh extract embedding cho người mới chỉ đi ngang.
                self._update_zone_states(zones, zone_counts)

                # 7. ReID chỉ xử lý detection có track_id, nằm trong zone và zone
                #    đó đã OCCUPIED nếu policy `require_occupied_zone` đang bật.
                detection_frame = self._apply_reid(
                    camera_id=camera.id,
                    detection_frame=detection_frame,
                    zones=zones,
                    zone_names=zone_names,
                    frame_idx=result_index,
                )

                # 8. Xây snapshot zone occupancy theo global_id để quyết định request robot.
                robot_requests = self._update_zone_occupancy(
                    camera=camera,
                    detection_frame=detection_frame,
                    zones=zones,
                    zone_names=zone_names,
                    frame_idx=result_index,
                )

                # LOGGER.debug("robot_requests=%s", robot_requests)

                # 9. Lưu snapshot mới nhất cho consumer bên ngoài đọc, ví dụ
                #    WebSocket preview hoặc robot sender trong bước refactor sau.
                self._update_runtime_payloads(
                    camera,
                    detection_frame,
                    zones,
                    zone_counts,
                )

                if self.config.verbose:
                    LOGGER.info(
                        "Camera: %s, Object: %s, Tracked: %s, Zones: %s, FPS: %.1f",
                        camera.name,
                        detection_frame.count,
                        detection_frame.tracked_count,
                        _format_zone_counts(zone_counts),
                        fps,
                    )
                    if robot_requests:
                        LOGGER.info("Robot service requests: %s", robot_requests)

                if self.config.show:
                    # 10. Preview debug: vẽ polygon zone, bbox/label và status bar.
                    self._show_detection_frame(camera, detection_frame, zone_names, fps)

        except KeyboardInterrupt:
            LOGGER.info("Ctrl+C received, stopping detection runtime.")
        finally:
            # 11. Dù loop kết thúc vì lý do nào cũng cleanup detector/OpenCV.
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

        LOGGER.info("Detect runtime stopped.")

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
            source     = self.config.source,
            model_size = self.config.model_size,
            batch_size = int(self.config.batch_size),
            conf       = float(self.config.conf),
            vid_stride = int(self.config.vid_stride),
            tracker    = self.config.tracker,
            persist    = bool(self.config.persist),
            verbose    = bool(self.config.verbose),
        )

        self.detector = YoloDetector(yolo_config)

        self.zone_state_machine = ZoneStateMachine(
            confirm_enter_time            = float(self.config.confirm_enter_time),
            confirm_exit_time             = float(self.config.confirm_exit_time),
            pending_enter_miss_grace_time = float(self.config.pending_enter_miss_grace_time),
        )
        self.reid_pipeline = self._build_reid_pipeline()

        self.state.reset()

        LOGGER.info(" RUNTIME CONFIGURATION ".center(77, LINE_CHAR))
        LOGGER.info("Config path                    : %s", self.config.config_path)
        LOGGER.info("Source                         : %s", self.config.source)
        LOGGER.info("Model size                     : %s", self.config.model_size)
        LOGGER.info("Batch size                     : %s", self.config.batch_size)
        LOGGER.info("Confidence threshold           : %s", self.config.conf)
        LOGGER.info("Video stride                   : %s", self.config.vid_stride)
        LOGGER.info("Show                           : %s", self.config.show)
        LOGGER.info("Use tracking                   : %s", self.config.use_tracking)
        if self.config.use_tracking:
            LOGGER.info("Tracker                        : %s", self.config.tracker)
            LOGGER.info("Persist tracker                : %s", self.config.persist)
        LOGGER.info("Enable ReID                    : %s", self.config.reid_config.enabled)
        if self.config.reid_config.enabled:
            LOGGER.info("ReID zone only                 : %s", self.config.reid_config.zone_only)
            LOGGER.info("ReID require occupied zone     : %s", self.config.reid_config.require_occupied_zone)
            LOGGER.info("ReID model path                : %s", self.config.reid_config.model_path or "default")
            LOGGER.info("ReID device                    : %s", self.config.reid_config.device)
            LOGGER.info("ReID embedding batch size      : %s", self.config.reid_config.embedding_batch_size)
            LOGGER.info("ReID max reverify misses       : %s", self.config.reid_config.max_reverify_misses)
        LOGGER.info("Zone check mode                : %s", self.config.zone_check_mode)
        LOGGER.info("Confirm enter time             : %s", self.config.confirm_enter_time)
        LOGGER.info("Confirm exit time              : %s", self.config.confirm_exit_time)
        LOGGER.info("Pending enter miss grace time  : %s",self.config.pending_enter_miss_grace_time,)
        LOGGER.info("Number of cameras              : %s", len(self.cameras))
        LOGGER.info(LINE_CHAR * 77)

    def _build_stream(self):
        """Chọn stream detect hoặc ByteTrack tùy cấu hình runtime."""
        assert self.detector is not None

        if self.config.use_tracking or self.config.reid_config.enabled:
            return self.detector.track_stream()

        return self.detector.predict_stream()

    def _build_reid_pipeline(self) -> Optional[ReIdPipeline]:
        """Khởi tạo ReID pipeline nếu runtime bật ReID."""
        if not self.config.reid_config.enabled:
            return None

        return ReIdPipeline.from_config(self.config.reid_config)

    def _camera_for_result(self, result_index: int) -> Camera:
        """Map result đã flatten của Ultralytics về camera tương ứng."""
        return self.cameras[result_index % len(self.cameras)]

    def _show_detection_frame(
        self,
        camera: Camera,
        detection_frame: DetectionFrame,
        zone_names,
        fps: float,
    ) -> None:
        """Vẽ và hiển thị frame debug gồm zone + detection."""
        frame = extract_raw_frame(detection_frame)
        if frame is None:
            return

        draw_zones(frame, camera.zones)
        draw_detection_overlay(frame, detection_frame.detections, zone_names)
        draw_fps_label(frame, camera.name, fps, detection_frame.count)

        if self.config.show_scale != 1.0:
            frame = resize_frame(frame, self.config.show_scale)

        window_name = f"{unidecode(str(camera.name).strip())}"
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

    def _apply_reid(
        self,
        *,
        camera_id: str,
        detection_frame: DetectionFrame,
        zones,
        zone_names,
        frame_idx: int,
    ) -> DetectionFrame:
        """Chạy ReID stage và trả DetectionFrame đã enrich global_id nếu có."""
        if self.reid_pipeline is None:
            return detection_frame

        # Chọn candidate thỏa policy để crop/extract embedding.
        candidates = self.reid_pipeline.select_candidates(
            camera_id=str(camera_id),
            detection_frame=detection_frame,
            zone_names=zone_names,
            allowed_zone_names=self._allowed_reid_zone_names(zones),
        )
        
        # Lấy frame gốc.
        raw_frame = extract_raw_frame(detection_frame)
        
        # Update ReID và lấy assignments để enrich DetectionFrame. 
        assignments = self.reid_pipeline.update(
            frame=raw_frame,
            candidates=candidates,
            frame_idx=frame_idx,
        )

        if not assignments:
            return detection_frame

        return self.reid_pipeline.enrich_detection_frame(detection_frame, assignments)

    def _allowed_reid_zone_names(self, zones) -> set[str] | None:
        """
        Lấy tập zone được phép ReID theo policy hiện tại.

        Khi `require_occupied_zone=True`, candidate phải vừa nằm trong zone vừa
        thuộc zone đã OCCUPIED. Nếu tắt policy này thì selector giữ hành vi cũ.
        """
        if not self.config.reid_config.require_occupied_zone:
            return None

        return {
            zone.name
            for zone in zones
            if zone.state == ZoneState.OCCUPIED
        }

    def _update_zone_states(self, zones, zone_counts: Dict[str, int]) -> None:
        """Cập nhật state machine để mỗi zone có state mới nhất."""
        if self.zone_state_machine is None:
            return

        # Runtime mới chỉ cần side effect cập nhật `zone.state`; request robot
        # được tạo ở tầng occupancy phía sau.
        self.zone_state_machine.update(zones, zone_counts)

    def _update_zone_occupancy(
        self,
        *,
        camera: Camera,
        detection_frame: DetectionFrame,
        zones,
        zone_names,
        frame_idx: int,
    ) -> list:
        """Cập nhật tầng occupancy và lưu các request robot mới phát sinh."""
        snapshot = build_zone_occupancy_snapshot(
            camera=camera,
            detection_frame=detection_frame,
            zones=zones,
            zone_names=zone_names,
            frame_idx=frame_idx,
        )
        requests = self.zone_occupancy_manager.update(snapshot, zones)
        self.state.update_robot_requests(requests)

        return requests

    def _update_runtime_payloads(
        self,
        camera: Camera,
        detection_frame: DetectionFrame,
        zones,
        zone_counts: Dict[str, int],
    ) -> None:
        """Cập nhật snapshot WebSocket trong RuntimeState."""
        camera_payload = build_detection_websocket_payload(
            camera=camera,
            detection_frame=detection_frame,
            zones=zones,
            zone_counts=zone_counts,
        )
        self.state.update_camera_payload(camera.id, camera_payload)


# ─────────────────────────────────────────────────────────────────────────────
def build_detect_runtime_config_from_file(
    config_path: str,
    *,
    max_frames: Optional[int] = None,
    show: Optional[bool] = None,
    use_tracking: bool = False,
    tracker: str = "bytetrack.yaml",
    persist: bool = True,
    enable_reid: Optional[bool] = None,
) -> DetectRuntimeConfig:
    """Đọc YAML và chuyển thành DetectRuntimeConfig."""
    cfg = load_config(config_path)
    detector_cfg = cfg.get("detector", {})
    zone_cfg = cfg.get("zones_state_machine", {})
    reid_cfg = cfg.get("reid", {})
    streams_file = cfg.get("source", {}).get("streams_file", "configs/rtsp.streams")

    return DetectRuntimeConfig(
        config_path                   = config_path,
        source                        = str(streams_file),
        model_size                    = detector_cfg.get("model_size", "nano"),
        batch_size                    = int(detector_cfg.get("batch_size", 1)),
        conf                          = float(detector_cfg.get("conf", 0.5)),
        vid_stride                    = int(detector_cfg.get("vid_stride", 1)),
        show                          = bool(detector_cfg.get("show", False)) if show is None else show,
        show_scale                    = float(detector_cfg.get("show_scale", 1.0)),
        verbose                       = bool(detector_cfg.get("verbose", True)),
        use_tracking                  = use_tracking,
        tracker                       = tracker,
        persist                       = persist,
        reid_config                   = _build_reid_config(reid_cfg, enabled_override=enable_reid),
        zone_check_mode               = zone_cfg.get("zone_check_mode", "center"),
        confirm_enter_time            = float(zone_cfg.get("confirm_enter_time", 5.0)),
        confirm_exit_time             = float(zone_cfg.get("confirm_exit_time", 5.0)),
        pending_enter_miss_grace_time = float(zone_cfg.get("pending_enter_miss_grace_time", 1.5)),
        max_frames                    = max_frames,
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
    enable_reid: Optional[bool] = None,
) -> None:
    """Helper tiện cho script test: tạo runtime từ YAML rồi chạy detect-only."""
    runtime_config = build_detect_runtime_config_from_file(
        config_path,
        max_frames=max_frames,
        show=show,
        use_tracking=use_tracking,
        tracker=tracker,
        persist=persist,
        enable_reid=enable_reid,
    )
    DetectOnlyRuntime(runtime_config).run()


# ─────────────────────────────────────────────────────────────────────────────
def _build_reid_config(
    reid_cfg: Dict[str, Any],
    *,
    enabled_override: Optional[bool] = None,
) -> ReIdConfig:
    """Đọc block `reid` trong YAML thành ReIdConfig."""
    return ReIdConfig(
        enabled                   = bool(reid_cfg.get("enabled", False)) if enabled_override is None else enabled_override,
        zone_only                 = bool(reid_cfg.get("zone_only", True)),
        require_occupied_zone     = bool(reid_cfg.get("require_occupied_zone", True)),
        model_path                = reid_cfg.get("model_path"),
        device                    = str(reid_cfg.get("device", "auto")),
        embedding_batch_size      = int(reid_cfg.get("embedding_batch_size", 32)),
        buffer_min                = int(reid_cfg.get("buffer_min", 200)),
        grace_period              = int(reid_cfg.get("grace_period", 20)),
        update_interval           = int(reid_cfg.get("update_interval", 120)),
        max_buffer_size           = int(reid_cfg.get("max_buffer_size", 250)),
        gallery_cleanup_interval  = int(reid_cfg.get("gallery_cleanup_interval", 1800)),
        max_reverify_misses       = int(reid_cfg.get("max_reverify_misses", 2)),
        min_detection_conf        = float(reid_cfg.get("min_detection_conf", 0.50)),
        min_bbox_aspect_ratio     = float(reid_cfg.get("min_bbox_aspect_ratio", 0.18)),
        max_bbox_aspect_ratio     = float(reid_cfg.get("max_bbox_aspect_ratio", 1.50)),
        overlap_iou_threshold     = float(reid_cfg.get("overlap_iou_threshold", 0.25)),
        overlap_ioa_threshold     = float(reid_cfg.get("overlap_ioa_threshold", 0.45)),
        stable_bbox_window        = int(reid_cfg.get("stable_bbox_window", 100)),
        stable_center_shift_ratio = float(reid_cfg.get("stable_center_shift_ratio", 0.20)),
        stable_size_change_ratio  = float(reid_cfg.get("stable_size_change_ratio", 0.25)),
        laplacian_var_threshold   = float(reid_cfg.get("laplacian_var_threshold", 50.0)),
        sim_threshold_match       = float(reid_cfg.get("sim_threshold_match", 0.85)),
        sim_threshold_unsure      = float(reid_cfg.get("sim_threshold_unsure", 0.65)),
        ema_alpha                 = float(reid_cfg.get("ema_alpha", 0.75)),
        max_samples               = int(reid_cfg.get("max_samples", 5)),
        gallery_ttl_minutes       = float(reid_cfg.get("gallery_ttl_minutes", 2.0)),
    )


# ─────────────────────────────────────────────────────────────────────────────
def _format_zone_counts(zone_counts: Dict[str, int]) -> str:
    """Format zone_counts ngắn gọn cho log runtime."""
    if not zone_counts:
        return "-"

    return ", ".join(f"{key}={count}" for key, count in zone_counts.items())
