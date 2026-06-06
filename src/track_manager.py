from __future__ import annotations

import logging
from typing import Callable

import cv2
import numpy as np

from src.gallery_manager import Gallery
from src.reid_types import TrackerConfig, TrackState, TrackStatus
from src.reid_utils import normalize_embedding

logger = logging.getLogger(__name__)


class TrackManager:
    """
    Tầng 1 của pipeline ReID online.

    TrackManager nhận track_id tạm từ ByteTrack, gom embedding của từng track,
    rồi hỏi Gallery để đổi từ track_id tạm sang global_id bền vững.
    """

    def __init__(
        self,
        gallery: Gallery,
        embedding_function: Callable[[np.ndarray], np.ndarray],
        config: TrackerConfig | None = None,
    ):
        self.gallery = gallery
        self.embedding_function = embedding_function
        self.cfg = config or TrackerConfig()

        self.active_tracks: dict[int, TrackState] = {}
        self._total_confirmed = 0

    def update(
        self,
        frame: np.ndarray,
        bytetrack_results: list[tuple[int, tuple, float]],
        frame_idx: int,
    ) -> dict[int, TrackState]:
        """
        Cập nhật toàn bộ track trong một frame.

        bytetrack_results có dạng: [(track_id, bbox_xyxy, confidence), ...].
        """
        alive_ids: set[int] = set()
        current_bboxes = {track_id: bbox for track_id, bbox, _ in bytetrack_results}

        # Mỗi detection đã có track_id từ ByteTrack sẽ được xử lý riêng.
        for track_id, bbox, conf in bytetrack_results:
            alive_ids.add(track_id)
            self._process_track(
                frame,
                track_id,
                bbox,
                conf,
                frame_idx,
                current_bboxes,
            )

        # Track nào biến mất lâu hơn grace_period thì xóa khỏi active_tracks.
        self._cleanup_dead_tracks(alive_ids, frame_idx)

        # Dọn gallery định kỳ để tránh giữ ID cũ mãi trong một session dài.
        if frame_idx % 1800 == 0:
            self.gallery.cleanup_old_entries(frame_idx)

        return self.active_tracks

    def _process_track(
        self,
        frame: np.ndarray,
        track_id: int,
        bbox: tuple,
        conf: float,
        frame_idx: int,
        current_bboxes: dict[int, tuple],
    ) -> None:
        """Xử lý một track_id: cập nhật bbox, crop người, extract embedding."""
        # Tạo TrackState lần đầu khi ByteTrack sinh ra track_id mới.
        if track_id not in self.active_tracks:
            self.active_tracks[track_id] = TrackState(
                track_id=track_id,
                last_seen=frame_idx,
            )

        track = self.active_tracks[track_id]
        track.frame_count += 1
        track.last_seen = frame_idx
        track.bbox = bbox
        track.confidence = float(conf)
        track.add_bbox(bbox, self.cfg.stable_bbox_window)

        # Crop người từ frame BGR gốc rồi đưa vào ReID model nếu đủ chất lượng.
        crop = self._crop(frame, bbox)
        if crop.size == 0:
            return

        # Chỉ lấy embedding ở frame có bbox đủ tốt; frame xấu vẫn giữ track sống.
        if not self._is_bbox_quality(
            track,
            bbox,
            conf,
            frame.shape,
            current_bboxes,
            crop,
        ):
            return

        # Chuẩn hóa lần nữa để bảo vệ pipeline nếu embedding_function trả raw vector.
        embedding = normalize_embedding(self.embedding_function(crop))
        track.add_embedding(embedding, frame_idx, self.cfg.max_buffer_size)

        # Track mới gom đủ embedding thì query Gallery để lấy global_id.
        if track.status in (TrackStatus.NEW, TrackStatus.UNCERTAIN):
            self._try_confirm(track, frame_idx)
        elif track.status == TrackStatus.CONFIRMED:
            # Track đã confirm thì chỉ refresh Gallery theo chu kỳ.
            self._maybe_refresh_gallery(track, embedding, frame_idx)

    def _is_bbox_quality(
        self,
        track: TrackState,
        bbox: tuple,
        conf: float,
        frame_shape: tuple,
        current_bboxes: dict[int, tuple],
        crop: np.ndarray,
    ) -> bool:
        """
        Kiểm tra bbox có đủ tốt để crop và extract embedding hay không.

        Một bbox tốt ở đây nghĩa là: không sát mép, không đè lên người khác,
        track đủ ổn định vài frame gần nhất, và crop đủ sắc nét.
        """
        if not self._is_bbox_geometry_quality(bbox, conf, frame_shape):
            return False
        if self._is_near_frame_edge(bbox, frame_shape):
            return False
        if self._has_blocking_overlap(track.track_id, bbox, current_bboxes):
            return False
        if not self._is_bbox_stable(track):
            return False
        return self._is_crop_sharp(crop)

    def _is_bbox_geometry_quality(
        self,
        bbox: tuple,
        conf: float,
        frame_shape: tuple,
    ) -> bool:
        """Lọc nhanh bbox quá nhỏ, confidence thấp hoặc tỉ lệ quá dị."""
        x1, y1, x2, y2 = bbox
        width = x2 - x1
        height = y2 - y1
        frame_height, frame_width = frame_shape[:2]

        if conf < self.cfg.min_detection_conf:
            return False
        if width < self.cfg.min_bbox_width or height < self.cfg.min_bbox_height:
            return False
        if height <= 0:
            return False

        aspect_ratio = width / height
        if not (
            self.cfg.min_bbox_aspect_ratio
            <= aspect_ratio
            <= self.cfg.max_bbox_aspect_ratio
        ):
            return False

        if x2 <= 0 or y2 <= 0 or x1 >= frame_width or y1 >= frame_height:
            return False
        return True

    def _is_near_frame_edge(self, bbox: tuple, frame_shape: tuple) -> bool:
        """Bỏ người quá sát mép vì crop thường bị cụt thân."""
        x1, y1, x2, y2 = bbox
        frame_height, frame_width = frame_shape[:2]
        margin_x = frame_width * self.cfg.edge_margin_ratio
        margin_y = frame_height * self.cfg.edge_margin_ratio

        return (
            x1 < margin_x
            or y1 < margin_y
            or x2 > frame_width - margin_x
            or y2 > frame_height - margin_y
        )

    def _has_blocking_overlap(
        self,
        track_id: int,
        bbox: tuple,
        current_bboxes: dict[int, tuple],
    ) -> bool:
        """
        Bỏ bbox đang đè lên bbox người khác.

        IoU cao nghĩa là hai bbox cùng chiếm vùng tương tự. IoA cao bắt được case
        một bbox nhỏ bị che nhiều bởi bbox lớn dù IoU tổng thể không quá cao.
        """
        for other_track_id, other_bbox in current_bboxes.items():
            if other_track_id == track_id:
                continue

            iou, ioa = self._bbox_overlap_scores(bbox, other_bbox)
            if (
                iou >= self.cfg.overlap_iou_threshold
                or ioa >= self.cfg.overlap_ioa_threshold
            ):
                return True
        return False

    def _is_bbox_stable(self, track: TrackState) -> bool:
        """Chỉ nhận embedding khi bbox ổn định trong vài frame gần nhất."""
        history = track.bbox_history
        if len(history) < self.cfg.stable_bbox_window:
            return False

        boxes = np.asarray(history, dtype=np.float32)
        widths = boxes[:, 2] - boxes[:, 0]
        heights = boxes[:, 3] - boxes[:, 1]
        centers = np.column_stack(
            ((boxes[:, 0] + boxes[:, 2]) / 2, (boxes[:, 1] + boxes[:, 3]) / 2)
        )

        avg_diag = float(np.mean(np.hypot(widths, heights)))
        if avg_diag <= 1e-6:
            return False

        center_distances = np.linalg.norm(centers - centers.mean(axis=0), axis=1)
        max_center_shift = float(center_distances.max()) / avg_diag
        if max_center_shift > self.cfg.stable_center_shift_ratio:
            return False

        areas = widths * heights
        mean_area = float(np.mean(areas))
        if mean_area <= 1e-6:
            return False

        size_change = float(np.std(areas) / mean_area)
        return size_change <= self.cfg.stable_size_change_ratio

    def _is_crop_sharp(self, crop: np.ndarray) -> bool:
        """Dùng Laplacian variance để bỏ crop bị mờ/rung."""
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        return sharpness >= self.cfg.laplacian_var_threshold

    @staticmethod
    def _bbox_overlap_scores(bbox_a: tuple, bbox_b: tuple) -> tuple[float, float]:
        """Trả về (IoU, IoA nhỏ nhất) giữa hai bbox."""
        ax1, ay1, ax2, ay2 = bbox_a
        bx1, by1, bx2, by2 = bbox_b

        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)
        inter_width = max(0.0, inter_x2 - inter_x1)
        inter_height = max(0.0, inter_y2 - inter_y1)
        inter_area = inter_width * inter_height

        area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
        area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        if area_a <= 0 or area_b <= 0 or inter_area <= 0:
            return 0.0, 0.0

        union = area_a + area_b - inter_area
        iou = inter_area / union if union > 0 else 0.0
        ioa = inter_area / min(area_a, area_b)
        return float(iou), float(ioa)

    def _try_confirm(self, track: TrackState, frame_idx: int) -> None:
        """Nếu track có đủ embedding tốt, gán hoặc tạo global_id trong Gallery."""
        if track.good_frame_count < self.cfg.buffer_min:
            return

        track.status = TrackStatus.PENDING
        # mean_embedding đã normalize lại, tránh vector trung bình bị lệch norm.
        create_on_uncertain = len(track.embedding_buffer) >= self.cfg.max_buffer_size
        result = self.gallery.resolve_identity(
            track.mean_embedding(),
            frame_idx,
            create_on_uncertain=create_on_uncertain,
        )

        if result.status == "uncertain":
            track.status = TrackStatus.UNCERTAIN
            logger.info(
                "Track %s UNCERTAIN -> candidate_global_id=%s "
                "(sim=%.3f, frame=%s, good_frames=%s)",
                track.track_id,
                result.global_id,
                result.similarity,
                frame_idx,
                track.good_frame_count,
            )
            return

        if result.global_id is None:
            raise RuntimeError("Gallery resolved identity without a global_id")

        track.global_id = result.global_id
        track.status = TrackStatus.CONFIRMED
        track.confirmed_at = frame_idx
        self._total_confirmed += 1

        logger.info(
            "Track %s CONFIRMED -> global_id=%s "
            "(status=%s, sim=%.3f, frame=%s, good_frames=%s)",
            track.track_id,
            result.global_id,
            result.status,
            result.similarity,
            frame_idx,
            track.good_frame_count,
        )

    def _maybe_refresh_gallery(
        self,
        track: TrackState,
        embedding: np.ndarray,
        frame_idx: int,
    ) -> None:
        """Cập nhật embedding đại diện của global_id theo chu kỳ."""
        frames_since = track.frames_since_confirmed(frame_idx)
        if frames_since > 0 and frames_since % self.cfg.update_interval == 0:
            if track.global_id is None:
                return
            self.gallery.update_entry(track.global_id, embedding, frame_idx)

    def _cleanup_dead_tracks(self, alive_ids: set[int], frame_idx: int) -> None:
        """Xóa track_id tạm đã mất dấu quá lâu khỏi bộ nhớ active."""
        dead = [
            tid
            for tid, track in self.active_tracks.items()
            if tid not in alive_ids
            and (frame_idx - track.last_seen) > self.cfg.grace_period
        ]
        for tid in dead:
            logger.debug(
                "Track %s removed (global_id=%s)",
                tid,
                self.active_tracks[tid].global_id,
            )
            del self.active_tracks[tid]

    @staticmethod
    def _crop(frame: np.ndarray, bbox: tuple) -> np.ndarray:
        """Crop bbox và clamp tọa độ để không vượt biên ảnh."""
        x1, y1, x2, y2 = map(int, bbox)
        height, width = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(width, x2), min(height, y2)
        return frame[y1:y2, x1:x2]

    def get_confirmed_tracks(self) -> dict[int, TrackState]:
        """Trả về các track đã có global_id, tiện cho render hoặc logging."""
        return {
            tid: track
            for tid, track in self.active_tracks.items()
            if track.is_confirmed()
        }

    def __repr__(self) -> str:
        confirmed = sum(
            1 for track in self.active_tracks.values() if track.is_confirmed()
        )
        return (
            f"<TrackManager active={len(self.active_tracks)} "
            f"confirmed={confirmed} "
            f"total_ever={self._total_confirmed}>"
        )
