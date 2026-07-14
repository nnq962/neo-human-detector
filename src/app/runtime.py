"""Runtime: MediaSources → YOLO → Zone → ReID → Robot dispatch → Output."""

from __future__ import annotations

import numpy as np
import threading
from typing import TYPE_CHECKING, Dict, List, Optional

import cv2
from unidecode import unidecode

from src.app.datatypes import RuntimeConfig
from src.app.runtime_state import build_camera_detection_payload, runtime_state
from src.app.utils import build_runtime_config
from src.camera_initializer import Camera, load_cameras_from_config
from src.detection.datatypes import InferenceFrame
from src.detection.yolo_detector import YoloDetector, YoloDetectorConfig
from src.dispatch_decision import (
    DispatchDecisionEngine,
    ReIdDecisionPolicy,
    ZoneOnlyDecisionPolicy,
)
from src.media_sources import MediaSources
from src.reid import ReIdPipeline
from src.robot_dispatch_v2 import RobotDispatcherV2
from src.visualization import (
    draw_detections,
    draw_status_bar,
    draw_zones,
)
from src.zones_management import ZoneState, ZoneStateMachine, assign_detections_to_zones
from utils import LOGGER, load_config, LINE_CHAR


if TYPE_CHECKING:
    from uart_v2.uart_manager import UartManagerV2


# ─────────────────────────────────────────────────────────────────────────────
class Runtime:

    def __init__(
        self,
        config: RuntimeConfig,
        *,
        robot_uart: Optional["UartManagerV2"] = None,
    ):
        self.config = config
        self.cameras: List[Camera] = []
        self.detector: Optional[YoloDetector] = None
        self.media_sources: Optional[MediaSources] = None
        self.zone_machines: Dict[str, ZoneStateMachine] = {}
        self.reid_pipeline: Optional[ReIdPipeline] = None
        self.robot_dispatcher: Optional[RobotDispatcherV2] = None
        self._robot_uart = robot_uart
        self.is_running = False
        self._stop_requested = threading.Event()
        self._fps_tracker: Dict[str, float] = {}
        self._frame_counters: Dict[str, int] = {}

    # ─────────────────────────────────────────────────────────────────────────
    def run(self) -> None:
        """Chạy vòng lặp detect cho đến khi hết stream hoặc Ctrl+C."""
        self._stop_requested.clear()
        try:
            self._prepare()
        except Exception:
            # _prepare() có thể đã mở media, model hoặc UART trước khi lỗi.
            self.stop()
            raise

        if self._stop_requested.is_set():
            self.stop()
            return

        self.is_running = True

        try:
            assert self.detector is not None
            assert self.media_sources is not None

            predict_function = self.detector.track_batch

            if self._stop_requested.is_set():
                return

            with self.media_sources:
                for frames, metas in self.media_sources:
                    if self._stop_requested.is_set() or not self.is_running:
                        break

                    # Inference
                    detection_frames = predict_function(frames)
                    self._validate_batch_lengths(frames, metas, detection_frames)
                    batch_payload: dict[str, dict] = {}

                    # Chỉ retry decision tồn đọng từ các batch trước. Decision mới
                    # của batch hiện tại sẽ được thử ngay trong process_zones().
                    if self.robot_dispatcher is not None:
                        self.robot_dispatcher.tick()

                    for frame, meta, detection_frame, camera in zip(
                        frames, metas, detection_frames, self.cameras
                    ):
                        detection_frame.camera_id = camera.id
                        fps = self._update_fps(camera.id, meta.timestamp)

                        zone_names: List[Optional[str]] = []
                        if camera.zones:
                            # Gắn detection vào zone.
                            zone_names, zone_counts = assign_detections_to_zones(
                                detection_frame.detections,
                                camera.zones,
                                task=self.config.detection.task,
                            )

                            # Cập nhật state machine cho mỗi zone dựa trên số lượng detection bên trong.
                            self.zone_machines[camera.id].update(camera.zones, zone_counts)

                        # Chạy ReID nếu được bật.
                        detection_frame = self._run_reid(
                            frame=frame,
                            camera=camera,
                            detection_frame=detection_frame,
                            zone_names=zone_names,
                        )

                        # Robot dispatcher
                        if camera.zones and self.robot_dispatcher is not None:
                            self.robot_dispatcher.process_zones(
                                camera.zones,
                                detections=detection_frame.detections,
                                zone_names=zone_names,
                            )

                        # ws/runtime/bboxes
                        batch_payload[camera.id] = build_camera_detection_payload(
                            camera=camera,
                            detection_frame=detection_frame,
                            timestamp=meta.timestamp,
                            zone_names=zone_names,
                        )

                        # Debug log
                        if self.config.detection.verbose:
                            matched = sum(
                                1 for d in detection_frame.detections if d.global_id is not None
                            )
                            LOGGER.info(
                                "Camera: %s | persons: %d | tracked: %d | reid: %d | fps: %.1f",
                                camera.name,
                                detection_frame.count,
                                detection_frame.tracked_count,
                                matched,
                                fps,
                            )

                        # Debug preview
                        if self.config.preview.enabled:
                            self._render(frame, camera, detection_frame, fps)

                    if batch_payload:
                        runtime_state.publish_detection_batch(batch_payload)

        except KeyboardInterrupt:
            LOGGER.info("Ctrl+C — stopping runtime.")
        finally:
            self.stop()

    # ─────────────────────────────────────────────────────────────────────────
    def stop(self) -> None:
        self._stop_requested.set()
        self.is_running = False

        if self.media_sources is not None:
            try:
                self.media_sources.request_stop()
            except Exception:
                pass
            self.media_sources = None

        if self.detector is not None:
            self.detector.close()
            self.detector = None

        if self.reid_pipeline is not None:
            self.reid_pipeline.close()
            self.reid_pipeline = None

        if self.robot_dispatcher is not None:
            self.robot_dispatcher.close()
            self.robot_dispatcher = None

        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

        runtime_state.clear()
        LOGGER.info("Runtime stopped.")

    # ─────────────────────────────────────────────────────────────────────────
    def request_stop(self) -> None:
        """Signal the runtime loop to stop without closing model resources."""
        self._stop_requested.set()
        self.is_running = False

        if self.media_sources is not None:
            try:
                self.media_sources.release()
            except Exception:
                pass

    # ── setup ─────────────────────────────────────────────────────────────────
    def _prepare(self) -> None:
        cfg = load_config(self.config.config_path)
        self.cameras = load_cameras_from_config(cfg, warn_on_empty_zones=False)

        if not self.cameras:
            raise RuntimeError("Không có camera enabled hợp lệ.")

        det = self.config.detection
        if len(self.cameras) != det.batch_size:
            raise ValueError(
                f"Số camera ({len(self.cameras)}) phải khớp batch_size ({det.batch_size})."
            )

        self.media_sources = MediaSources(
            [cam.source for cam in self.cameras],
            reconnect=True,
            reconnect_forever=True,
            reconnect_delay=2.0,
        )

        self.detector = YoloDetector(
            YoloDetectorConfig(
                task       = det.task,
                model_size = det.model_size,
                batch_size = det.batch_size,
                conf       = det.conf,
                tracker    = det.tracker,
            )
        )

        zsm = self.config.zone_state_machine
        self.zone_machines = {
            cam.id: ZoneStateMachine(
                confirm_enter_time            = zsm.confirm_enter_time,
                confirm_exit_time             = zsm.confirm_exit_time,
                pending_enter_miss_grace_time      = zsm.pending_enter_miss_grace_time,
            )
            for cam in self.cameras
        }
        self._frame_counters = {cam.id: 0 for cam in self.cameras}

        if self.config.reid.enabled:
            self.reid_pipeline = ReIdPipeline.from_config(self.config.reid)

        if self.config.robot_dispatch.enabled:
            self.robot_dispatcher = self._build_robot_dispatcher(cfg)

        if self.config.preview.enabled:
            preview = self.config.preview
            for cam in self.cameras:
                win_name = unidecode(str(cam.name).strip())
                cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(win_name, preview.window_width, preview.window_height)

        # ── log ───────────────────────────────────────────────────────────────
        LOGGER.info(" RUNTIME CONFIGURATION ".center(77, LINE_CHAR))
        LOGGER.info("CONFIG PATH: %s", self.config.config_path)

        LOGGER.info("DETECTOR")
        LOGGER.info("   → Task          : %s", det.task)
        LOGGER.info("   → Model size    : %s", det.model_size)
        LOGGER.info("   → Batch size    : %d", det.batch_size)
        LOGGER.info("   → Confidence    : %.2f", det.conf)
        LOGGER.info("   → Tracker       : %s", det.tracker)

        LOGGER.info("ZONE STATE MACHINE")
        LOGGER.info("   → Confirm enter : %.1fs", zsm.confirm_enter_time)
        LOGGER.info("   → Confirm exit  : %.1fs", zsm.confirm_exit_time)
        LOGGER.info("   → Miss grace    : %.1fs", zsm.pending_enter_miss_grace_time)

        LOGGER.info("CAMERAS")
        for cam in self.cameras:
            n = len(cam.zones)
            LOGGER.info("   → %s : %s | (%d zone%s)", cam.name, cam.source, n, "s" if n != 1 else "")

        reid = self.config.reid
        LOGGER.info("REID")
        LOGGER.info("   → Enabled       : %s", reid.enabled)
        if reid.enabled:
            LOGGER.info("   → Zone only     : %s", reid.zone_only)
            LOGGER.info("   → Device        : %s", reid.device)
            LOGGER.info("   → Buffer min    : %d", reid.buffer_min)
            LOGGER.info("   → Gallery TTL   : %.1f min", reid.gallery_ttl_minutes)

        robot = self.config.robot_dispatch
        LOGGER.info("ROBOT DISPATCH")
        LOGGER.info("   → Enabled       : %s", robot.enabled)
        LOGGER.info("   → Use ReID      : %s", robot.use_reid)
        LOGGER.info("   → ACK timeout   : %.2fs", robot.ack_timeout_seconds)
        LOGGER.info("   → Max retries   : %d", robot.max_retries)

        preview = self.config.preview
        LOGGER.info("PREVIEW")
        LOGGER.info("   → Show          : %s", preview.enabled)
        LOGGER.info("   → Window size   : %dx%d", preview.window_width, preview.window_height)

        LOGGER.info(LINE_CHAR * 77)
        LOGGER.info("Runtime started.")

    # ── per-frame ─────────────────────────────────────────────────────────────
    def _render(
        self,
        frame          : np.ndarray,
        camera         : Camera,
        detection_frame: InferenceFrame,
        fps            : float,
    ) -> None:
        canvas = frame.copy()

        if camera.zones:
            draw_zones(canvas, camera.zones)

        draw_detections(canvas, detection_frame.detections, draw_head_kps=False)

        draw_status_bar(
            canvas,
            camera_name=camera.name,
            fps=fps,
            detection_count=detection_frame.count,
        )

        cv2.imshow(unidecode(str(camera.name).strip()), canvas)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            self.is_running = False

    # ─────────────────────────────────────────────────────────────────────────
    def _build_robot_dispatcher(self, cfg: dict) -> RobotDispatcherV2:
        """Kết nối UART nhị phân và tạo RobotDispatcherV2."""
        robot_config = self.config.robot_dispatch
        if robot_config.use_reid and not self.config.reid.enabled:
            raise ValueError(
                "robot_dispatch.use_reid=true yêu cầu reid.enabled=true."
            )

        if self._robot_uart is None:
            from uart_v2.uart_manager import uart_manager_v2

            self._robot_uart = uart_manager_v2

        robot_uart = self._robot_uart

        uart_cfg = cfg.get("uart", {})
        if isinstance(uart_cfg, dict):
            connected = robot_uart.reconfigure(
                port=uart_cfg.get("port"),
                baudrate=uart_cfg.get("baudrate"),
            )
        else:
            connected = robot_uart.connect()

        if not connected:
            raise RuntimeError("Không thể kết nối UART V2 cho robot dispatcher.")

        policy = (
            ReIdDecisionPolicy()
            if robot_config.use_reid
            else ZoneOnlyDecisionPolicy()
        )
        decision_engine = DispatchDecisionEngine(policy=policy)
        return RobotDispatcherV2(
            robot_uart,
            decision_engine=decision_engine,
            ack_timeout_seconds=robot_config.ack_timeout_seconds,
            max_retries=robot_config.max_retries,
        )

    # ─────────────────────────────────────────────────────────────────────────
    def _update_fps(self, camera_id: str, timestamp: float) -> float:
        prev = self._fps_tracker.get(camera_id)
        self._fps_tracker[camera_id] = timestamp
        if prev is None:
            return 0.0
        return 1.0 / max(timestamp - prev, 1e-6)

    # ─────────────────────────────────────────────────────────────────────────
    def _validate_batch_lengths(
        self,
        frames: List[np.ndarray],
        metas: list,
        detection_frames: List[InferenceFrame],
    ) -> None:
        """Fail fast nếu media batch, detection batch và camera config bị lệch."""
        lengths = {
            "frames": len(frames),
            "metas": len(metas),
            "detection_frames": len(detection_frames),
            "cameras": len(self.cameras),
        }
        if len(set(lengths.values())) != 1:
            raise RuntimeError(f"Runtime batch length mismatch: {lengths}")

    # ─────────────────────────────────────────────────────────────────────────
    def _run_reid(
        self,
        *,
        frame: np.ndarray,
        camera: Camera,
        detection_frame: InferenceFrame,
        zone_names: List[Optional[str]],
    ) -> InferenceFrame:
        """Chạy ReID nếu được bật, ngược lại trả nguyên detection_frame."""
        if self.reid_pipeline is None:
            return detection_frame
        if self.config.reid.zone_only and not camera.zones:
            return detection_frame

        allowed_zone_names = self._allowed_reid_zone_names(camera)
        if allowed_zone_names is not None and not allowed_zone_names:
            return detection_frame

        self._frame_counters[camera.id] += 1
        return self.reid_pipeline.process(
            camera_id=camera.id,
            frame=frame,
            detection_frame=detection_frame,
            zone_names=zone_names,
            frame_idx=self._frame_counters[camera.id],
            allowed_zone_names=allowed_zone_names,
        )

    # ─────────────────────────────────────────────────────────────────────────
    def _allowed_reid_zone_names(self, camera: Camera) -> Optional[set[str]]:
        """
        Lọc zone đang occupied.
        """
        if not self.config.reid.require_occupied_zone:
            return None
        return {
            zone.name
            for zone in camera.zones
            if zone.state == ZoneState.OCCUPIED
        }


# ─────────────────────────────────────────────────────────────────────────────
def run(
    config_path: str = "configs/test.yaml",
    *,
    show: Optional[bool] = None,
) -> None:
    """Shortcut: build config từ YAML rồi chạy runtime ngay."""
    Runtime(build_runtime_config(config_path, show=show)).run()
