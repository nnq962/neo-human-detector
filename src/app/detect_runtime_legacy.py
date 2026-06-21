"""
Runtime detect + zone cho pipeline mới.

Runtime này nối các phần đã tách module: camera loader, MediaSources, YOLO
detector, zone geometry/state machine, WebSocket payload snapshot và
visualization debug.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from unidecode import unidecode
import cv2

from src.media_sources import Camera, load_cameras_from_config
from src.app.runtime_state import RuntimeState
from src.detection import DetectionFrame, YoloDetector, YoloDetectorConfig
from src.media_sources import MediaSources
from src.outputs import (
    build_detection_websocket_payload,
    draw_detection_overlay,
    draw_fps_label,
    draw_zones,
    extract_raw_frame,
    resize_frame,
)
from src.reid import ReIdConfig, ReIdPipeline
from src.zones_management import (
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

    `show`/`show_scale` phục vụ debug preview bằng OpenCV.
    `source` đã bị bỏ — RTSP source lấy trực tiếp từ camera config.
    """

    config_path                  : str           = "configs/test.yaml"
    model_size                   : str           = "nano"
    batch_size                   : int           = 1
    conf                         : float         = 0.5
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

    Frame được đọc bởi MediaSources, sau đó đưa vào YOLO theo batch.
    Kết quả được xử lý per-camera: zone assignment, state machine, ReID,
    occupancy và snapshot WebSocket.
    """

    def __init__(self, config: DetectRuntimeConfig):
        self.config = config
        self.cameras: List[Camera] = []
        self.detector: Optional[YoloDetector] = None
        self.media_sources: Optional[MediaSources] = None
        self.zone_state_machine: Optional[ZoneStateMachine] = None
        self.zone_occupancy_manager = ZoneOccupancyManager()
        self.reid_pipeline: Optional[ReIdPipeline] = None
        self.state = RuntimeState()
        self.is_running = False
        self._prev_times_by_camera: Dict[str, float] = {}

    @property
    def latest_ws_payload(self) -> Dict[str, Any]:
        return self.state.get_websocket_snapshot()

    @property
    def latest_robot_requests(self) -> list:
        return self.state.get_robot_requests_snapshot()

    def run(self) -> None:
        """Chạy vòng lặp detect + zone tới khi hết stream, Ctrl+C hoặc max_frames."""
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
            assert self.media_sources is not None

            predict_fn = (
                self.detector.track_batch
                if (self.config.use_tracking or self.config.reid_config.enabled)
                else self.detector.predict_batch
            )

            with self.media_sources:
                for frame_idx, (frames, metas) in enumerate(self.media_sources):
                    if not self.is_running:
                        break

                    if self._should_stop_by_frame_limit(frame_idx):
                        LOGGER.info("Đã đạt max_frames=%s, dừng.", self.config.max_frames)
                        break

                    # YOLO xử lý cả batch một lần, trả list DetectionFrame
                    # theo đúng thứ tự cameras.
                    detection_frames = predict_fn(frames)

                    for i, (detection_frame, camera, meta) in enumerate(
                        zip(detection_frames, self.cameras, metas)
                    ):
                        detection_frame.camera_id = camera.id
                        fps   = self._update_fps(camera.id, meta.timestamp)
                        zones = camera.zones

                        zone_names, zone_counts = assign_detections_to_zones(
                            detection_frame.detections,
                            zones,
                            self.config.zone_check_mode,
                        )

                        self._update_zone_states(zones, zone_counts)

                        detection_frame = self._apply_reid(
                            camera_id=camera.id,
                            detection_frame=detection_frame,
                            zones=zones,
                            zone_names=zone_names,
                            frame_idx=frame_idx,
                        )

                        robot_requests = self._update_zone_occupancy(
                            camera=camera,
                            detection_frame=detection_frame,
                            zones=zones,
                            zone_names=zone_names,
                            frame_idx=frame_idx,
                        )

                        LOGGER.debug("robot_requests=%s", robot_requests)

                        self._update_runtime_payloads(camera, detection_frame, zones, zone_counts)

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
                            self._show_detection_frame(camera, detection_frame, zone_names, fps)

        except KeyboardInterrupt:
            LOGGER.info("Ctrl+C received, stopping detection runtime.")
        finally:
            self.stop()

    def stop(self) -> None:
        """Dừng runtime và cleanup detector/MediaSources/OpenCV."""
        self.is_running = False
        self.state.mark_running(False)

        if self.media_sources is not None:
            try:
                self.media_sources.release()
            except Exception:
                pass
            self.media_sources = None

        if self.detector is not None:
            self.detector.close()
            self.detector = None

        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

        LOGGER.info("Detect runtime stopped.")

    # ── setup ─────────────────────────────────────────────────────────────────

    def _prepare(self) -> None:
        """Load camera, khởi tạo MediaSources, YoloDetector và zone state machine."""
        cfg = load_config(self.config.config_path)
        self.cameras = load_cameras_from_config(cfg, warn_on_empty_zones=True)

        if not self.cameras:
            raise RuntimeError("Không có camera enabled hợp lệ để chạy detect.")

        if len(self.cameras) != self.config.batch_size:
            raise ValueError(
                f"Số camera enabled phải khớp batch_size: "
                f"cameras={len(self.cameras)}, batch_size={self.config.batch_size}."
            )

        sources = [cam.source for cam in self.cameras]
        self.media_sources = MediaSources(
            sources,
            reconnect=True,
            reconnect_forever=True,
            reconnect_delay=2.0,
        )

        self.detector = YoloDetector(
            YoloDetectorConfig(
                model_size=self.config.model_size,
                batch_size=self.config.batch_size,
                conf=self.config.conf,
                tracker=self.config.tracker,
                persist=self.config.persist,
                verbose=self.config.verbose,
            )
        )

        self.zone_state_machine = ZoneStateMachine(
            confirm_enter_time            = float(self.config.confirm_enter_time),
            confirm_exit_time             = float(self.config.confirm_exit_time),
            pending_enter_miss_grace_time = float(self.config.pending_enter_miss_grace_time),
        )
        self.reid_pipeline = self._build_reid_pipeline()
        self.state.reset()

        LOGGER.info(" RUNTIME CONFIGURATION ".center(77, LINE_CHAR))
        LOGGER.info("Config path                    : %s", self.config.config_path)
        LOGGER.info("Model size                     : %s", self.config.model_size)
        LOGGER.info("Batch size                     : %s", self.config.batch_size)
        LOGGER.info("Confidence threshold           : %s", self.config.conf)
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
        LOGGER.info("Zone check mode                : %s", self.config.zone_check_mode)
        LOGGER.info("Confirm enter time             : %s", self.config.confirm_enter_time)
        LOGGER.info("Confirm exit time              : %s", self.config.confirm_exit_time)
        LOGGER.info("Pending enter miss grace time  : %s", self.config.pending_enter_miss_grace_time)
        LOGGER.info("Number of cameras              : %s", len(self.cameras))
        LOGGER.info(LINE_CHAR * 77)

    def _build_reid_pipeline(self) -> Optional[ReIdPipeline]:
        if not self.config.reid_config.enabled:
            return None
        return ReIdPipeline.from_config(self.config.reid_config)

    # ── per-camera processing ─────────────────────────────────────────────────

    def _show_detection_frame(
        self,
        camera: Camera,
        detection_frame: DetectionFrame,
        zone_names,
        fps: float,
    ) -> None:
        frame = extract_raw_frame(detection_frame)
        if frame is None:
            return

        draw_zones(frame, camera.zones)
        draw_detection_overlay(frame, detection_frame.detections, zone_names)
        draw_fps_label(frame, camera.name, fps, detection_frame.count)

        if self.config.show_scale != 1.0:
            frame = resize_frame(frame, self.config.show_scale)

        window_name = unidecode(str(camera.name).strip())
        cv2.imshow(window_name, frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            self.is_running = False

    def _update_fps(self, camera_id: str, current_time: float) -> float:
        prev_time = self._prev_times_by_camera.get(camera_id)
        self._prev_times_by_camera[camera_id] = current_time
        if prev_time is None:
            return 0.0
        return 1.0 / max(current_time - prev_time, 1e-6)

    def _should_stop_by_frame_limit(self, frame_idx: int) -> bool:
        return self.config.max_frames is not None and frame_idx >= self.config.max_frames

    def _apply_reid(
        self,
        *,
        camera_id: str,
        detection_frame: DetectionFrame,
        zones,
        zone_names,
        frame_idx: int,
    ) -> DetectionFrame:
        if self.reid_pipeline is None:
            return detection_frame

        candidates = self.reid_pipeline.select_candidates(
            camera_id=str(camera_id),
            detection_frame=detection_frame,
            zone_names=zone_names,
            allowed_zone_names=self._allowed_reid_zone_names(zones),
        )

        raw_frame = extract_raw_frame(detection_frame)

        assignments = self.reid_pipeline.update(
            frame=raw_frame,
            candidates=candidates,
            frame_idx=frame_idx,
        )

        if not assignments:
            return detection_frame

        return self.reid_pipeline.enrich_detection_frame(detection_frame, assignments)

    def _allowed_reid_zone_names(self, zones) -> Optional[set]:
        if not self.config.reid_config.require_occupied_zone:
            return None
        return {zone.name for zone in zones if zone.state == ZoneState.OCCUPIED}

    def _update_zone_states(self, zones, zone_counts: Dict[str, int]) -> None:
        if self.zone_state_machine is None:
            return
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

    detection_cfg = cfg.get("detection", {})
    preview_cfg   = cfg.get("preview", {})
    zone_cfg      = cfg.get("zone_state_machine", {})
    reid_cfg      = cfg.get("reid", {})

    return DetectRuntimeConfig(
        config_path                   = config_path,
        model_size                    = detection_cfg.get("model_size", "nano"),
        batch_size                    = int(detection_cfg.get("batch_size", 1)),
        conf                          = float(detection_cfg.get("conf", 0.5)),
        show                          = bool(preview_cfg.get("enabled", False)) if show is None else show,
        show_scale                    = float(preview_cfg.get("scale", 1.0)),
        verbose                       = bool(detection_cfg.get("verbose", True)),
        use_tracking                  = use_tracking,
        tracker                       = tracker,
        persist                       = persist,
        reid_config                   = _build_reid_config(reid_cfg, enabled_override=enable_reid),
        zone_check_mode               = zone_cfg.get("check_mode", "center"),
        confirm_enter_time            = float(zone_cfg.get("confirm_enter_time", 5.0)),
        confirm_exit_time             = float(zone_cfg.get("confirm_exit_time", 5.0)),
        pending_enter_miss_grace_time = float(zone_cfg.get("pending_enter_miss_grace", 1.5)),
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
    """Helper tiện cho script test: tạo runtime từ YAML rồi chạy detect."""
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
    """Đọc block `reid` (nested YAML) thành ReIdConfig."""
    embedding_cfg = reid_cfg.get("embedding", {})
    track_cfg     = reid_cfg.get("track",     {})
    quality_cfg   = reid_cfg.get("quality",   {})
    gallery_cfg   = reid_cfg.get("gallery",   {})

    return ReIdConfig(
        enabled                   = bool(reid_cfg.get("enabled", False)) if enabled_override is None else enabled_override,
        zone_only                 = bool(reid_cfg.get("zone_only", True)),
        require_occupied_zone     = bool(reid_cfg.get("require_occupied_zone", True)),
        model_path                = reid_cfg.get("model_path"),
        device                    = str(reid_cfg.get("device", "auto")),
        embedding_batch_size      = int(embedding_cfg.get("batch_size", 32)),
        buffer_min                = int(track_cfg.get("buffer_min", 200)),
        grace_period              = int(track_cfg.get("grace_period", 20)),
        update_interval           = int(track_cfg.get("update_interval", 120)),
        max_buffer_size           = int(track_cfg.get("max_buffer_size", 250)),
        gallery_cleanup_interval  = int(track_cfg.get("gallery_cleanup_interval", 1800)),
        max_reverify_misses       = int(track_cfg.get("max_reverify_misses", 2)),
        min_detection_conf        = float(quality_cfg.get("min_confidence", 0.50)),
        min_bbox_width            = float(quality_cfg.get("min_width", 30.0)),
        min_bbox_height           = float(quality_cfg.get("min_height", 70.0)),
        min_bbox_aspect_ratio     = float(quality_cfg.get("min_aspect_ratio", 0.18)),
        max_bbox_aspect_ratio     = float(quality_cfg.get("max_aspect_ratio", 1.50)),
        edge_margin_ratio         = float(quality_cfg.get("edge_margin_ratio", 0.02)),
        overlap_iou_threshold     = float(quality_cfg.get("overlap_iou_threshold", 0.25)),
        overlap_ioa_threshold     = float(quality_cfg.get("overlap_ioa_threshold", 0.45)),
        stable_bbox_window        = int(quality_cfg.get("stable_bbox_window", 100)),
        stable_center_shift_ratio = float(quality_cfg.get("stable_center_shift_ratio", 0.20)),
        stable_size_change_ratio  = float(quality_cfg.get("stable_size_change_ratio", 0.25)),
        laplacian_var_threshold   = float(quality_cfg.get("laplacian_var_threshold", 50.0)),
        sim_threshold_match       = float(gallery_cfg.get("sim_threshold_match", 0.85)),
        sim_threshold_unsure      = float(gallery_cfg.get("sim_threshold_unsure", 0.65)),
        ema_alpha                 = float(gallery_cfg.get("ema_alpha", 0.75)),
        max_samples               = int(gallery_cfg.get("max_samples", 5)),
        gallery_ttl_minutes       = float(gallery_cfg.get("ttl_minutes", 2.0)),
    )


# ─────────────────────────────────────────────────────────────────────────────
def _format_zone_counts(zone_counts: Dict[str, int]) -> str:
    if not zone_counts:
        return "-"
    return ", ".join(f"{key}={count}" for key, count in zone_counts.items())
