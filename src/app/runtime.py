"""
Runtime đơn giản: MediaSources → YOLO → Visualization.

Không có ReID, zone state machine hay WebSocket payload.
Dùng để kiểm tra nhanh model detection/pose và visualization.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional

import cv2
from unidecode import unidecode

from src.detection.detections import Detection, DetectionFrame
from src.detection.yolo_detector import YoloDetector, YoloDetectorConfig
from src.media_sources import Camera, MediaSources, load_cameras_from_config
from src.visualization import (
    draw_person_bboxes,
    draw_status_bar,
    draw_zones,
    resize_for_display,
)
from utils import LOGGER, load_config, LINE_CHAR


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RuntimeConfig:
    """Cấu hình runtime đơn giản detect + visualization."""

    config_path : str           = "configs/test.yaml"
    model_size  : str           = "nano"
    batch_size  : int           = 1
    conf        : float         = 0.5
    tracker     : str           = "bytetrack.yaml"
    persist     : bool          = True
    show        : bool          = False
    show_scale  : float         = 1.0
    verbose     : bool          = True


# ─────────────────────────────────────────────────────────────────────────────
class Runtime:
    """
    Runtime
    """

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.cameras: List[Camera] = []
        self.detector: Optional[YoloDetector] = None
        self.media_sources: Optional[MediaSources] = None
        self.is_running = False
        self._fps_tracker: Dict[str, float] = {}

    def run(self) -> None:
        """Chạy vòng lặp detect cho đến khi hết stream, Ctrl+C."""
        self._prepare()
        self.is_running = True

        try:
            assert self.detector is not None
            assert self.media_sources is not None

            predict_function = self.detector.track_batch

            with self.media_sources:
                # Vòng lặp duyệt qua các batch frame từ tất cả camera
                for frames, metas in self.media_sources:
                    if not self.is_running:
                        break

                    detection_frames = predict_function(frames)

                    for frame, meta, detection_frame, camera in zip(frames, metas, detection_frames, self.cameras):
                        detection_frame.camera_id = camera.id
                        fps = self._update_fps(camera.id, meta.timestamp)

                        if self.config.verbose:
                            LOGGER.info(
                                "Camera: %s | persons: %d | tracked: %d | fps: %.1f",
                                camera.name,
                                detection_frame.count,
                                detection_frame.tracked_count,
                                fps,
                            )

                        if self.config.show:
                            self._render(frame, camera, detection_frame, fps)

        except KeyboardInterrupt:
            LOGGER.info("Ctrl+C — stopping runtime.")
        finally:
            self.stop()

    def stop(self) -> None:
        """Dừng runtime và giải phóng tài nguyên."""
        self.is_running = False

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

        LOGGER.info("Runtime stopped.")

    # ── setup ─────────────────────────────────────────────────────────────────
    def _prepare(self) -> None:
        cfg = load_config(self.config.config_path)
        self.cameras = load_cameras_from_config(cfg, warn_on_empty_zones=False)

        if not self.cameras:
            raise RuntimeError("Không có camera enabled hợp lệ.")
        if len(self.cameras) != self.config.batch_size:
            raise ValueError(
                f"Số camera ({len(self.cameras)}) phải khớp batch_size ({self.config.batch_size})."
            )

        # Khởi tạo MediaSources với tất cả nguồn từ cameras
        self.media_sources = MediaSources(
            [cam.source for cam in self.cameras],
            reconnect=True,
            reconnect_forever=True,
            reconnect_delay=2.0,
        )

        # Khởi tạo YoloDetector
        self.detector = YoloDetector(
            YoloDetectorConfig(
                model_size=self.config.model_size,
                batch_size=self.config.batch_size,
                conf=self.config.conf,
                tracker=self.config.tracker,
                persist=self.config.persist,
            )
        )

        LOGGER.info(" RUNTIME CONFIGURATION ".center(77, LINE_CHAR))
        LOGGER.info("CONFIG PATH: %s", self.config.config_path)

        LOGGER.info("DETECTOR")
        LOGGER.info("   → Model size    : %s", self.config.model_size)
        LOGGER.info("   → Batch size    : %d", self.config.batch_size)
        LOGGER.info("   → Confidence    : %.2f", self.config.conf)
        LOGGER.info("   → Tracker       : %s", self.config.tracker)

        LOGGER.info("CAMERAS")
        for cam in self.cameras:
            n = len(cam.zones)
            LOGGER.info("   → %s        : %s | (%d zone%s)", cam.name, cam.source, n, "s" if n != 1 else "")

        LOGGER.info("PREVIEW")
        LOGGER.info("   → Show          : %s", self.config.show)
        LOGGER.info("   → Scale         : %.2f", self.config.show_scale)

        LOGGER.info(LINE_CHAR * 77)
        LOGGER.info("Runtime started.")

    # ── per-frame ─────────────────────────────────────────────────────────────
    def _render(
        self,
        frame          : np.ndarray,
        camera         : Camera,
        detection_frame: DetectionFrame,
        fps            : float,
    ) -> None:
        """Vẽ kết quả detection lên bản sao frame rồi hiển thị cửa sổ OpenCV."""
        canvas = frame.copy()

        if camera.zones:
            draw_zones(canvas, camera.zones)

        bboxes, track_ids, confs = _unpack_detections(detection_frame.detections)
        draw_person_bboxes(
            canvas,
            bboxes,
            track_ids=track_ids,
            confidences=confs,
        )

        draw_status_bar(
            canvas,
            camera_name=camera.name,
            fps=fps,
            detection_count=detection_frame.count,
        )

        if self.config.show_scale != 1.0:
            canvas = resize_for_display(canvas, self.config.show_scale)

        cv2.imshow(unidecode(str(camera.name).strip()), canvas)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            self.is_running = False

    def _update_fps(self, camera_id: str, timestamp: float) -> float:
        prev = self._fps_tracker.get(camera_id)
        self._fps_tracker[camera_id] = timestamp
        if prev is None:
            return 0.0
        return 1.0 / max(timestamp - prev, 1e-6)


# ─────────────────────────────────────────────────────────────────────────────
def _unpack_detections(
    detections: List[Detection],
) -> tuple[list, list, list]:
    """Tách list Detection thành 3 list riêng để truyền vào draw_person_bboxes."""
    bboxes    = [d.bbox       for d in detections]
    track_ids = [d.track_id   for d in detections]
    confs     = [d.confidence for d in detections]
    return bboxes, track_ids, confs


# ─────────────────────────────────────────────────────────────────────────────
def build_runtime_config(
    config_path: str = "configs/test.yaml",
    *,
    show        : Optional[bool] = None,
) -> RuntimeConfig:
    """Đọc YAML và tạo RuntimeConfig."""
    cfg          = load_config(config_path)
    detection    = cfg.get("detection", {})
    preview      = cfg.get("preview", {})

    return RuntimeConfig(
        config_path  = config_path,
        model_size   = detection.get("model_size", "nano"),
        batch_size   = int(detection.get("batch_size", 1)),
        conf         = float(detection.get("conf", 0.5)),
        show         = bool(preview.get("enabled", True)) if show is None else show,
        show_scale   = float(preview.get("scale", 1.0)),
        verbose      = bool(detection.get("verbose", True)),
    )


def run(
    config_path : str = "configs/test.yaml",
    *,
    show        : Optional[bool] = None,
) -> None:
    """Shortcut: build config từ YAML rồi chạy runtime ngay."""
    runtime_config = build_runtime_config(
        config_path,
        show=show,
    )
    # Run runtime
    Runtime(runtime_config).run()
