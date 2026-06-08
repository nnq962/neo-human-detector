"""
Track manager cho ReID online.

Manager nhận các candidate đã được runtime lọc theo zone, gom embedding cho từng
ByteTrack track tạm, rồi query IdentityGallery để đổi sang global_id bền vững.
"""

from __future__ import annotations

import logging
from typing import Callable

import cv2
import numpy as np

from src.reid.gallery import IdentityGallery
from src.reid.types import (
    BBoxXYXY,
    ReIdAssignment,
    ReIdCandidate,
    ReIdConfig,
    ReIdTrackKey,
    ReIdTrackState,
    ReIdTrackStatus,
)
from src.reid.utils import normalize_embedding


LOGGER = logging.getLogger(__name__)
EmbeddingFunction = Callable[[np.ndarray], np.ndarray]


# ─────────────────────────────────────────────────────────────────────────────
class ReIdTrackManager:
    """
    Quản lý track tạm từ ByteTrack và resolve sang global_id.

    `active_tracks` key theo `(camera_id, track_id)`, còn IdentityGallery là global
    chung để một người ở nhiều camera vẫn có thể nhận cùng global_id.
    """

    def __init__(
        self,
        gallery: IdentityGallery,
        embedding_function: EmbeddingFunction,
        config: ReIdConfig | None = None,
    ):
        self.gallery = gallery
        self.embedding_function = embedding_function
        self.config = config or ReIdConfig()
        self.active_tracks: dict[ReIdTrackKey, ReIdTrackState] = {}
        self._total_confirmed = 0

    def update(
        self,
        frame: np.ndarray,
        candidates: list[ReIdCandidate],
        frame_idx: int,
    ) -> dict[ReIdTrackKey, ReIdAssignment]:
        """
        Cập nhật ReID bằng danh sách candidate trong một frame.

        Chỉ candidate được truyền vào mới extract embedding. Runtime có thể lọc
        candidate trước, ví dụ chỉ bbox nằm trong zone.
        """
        alive_keys = {candidate.key for candidate in candidates}
        current_bboxes = {
            candidate.key: candidate.bbox
            for candidate in candidates
        }
        assignments: dict[ReIdTrackKey, ReIdAssignment] = {}

        for candidate in candidates:
            assignment = self._process_candidate(
                frame,
                candidate,
                frame_idx,
                current_bboxes,
            )
            assignments[candidate.key] = assignment

        self.cleanup_dead_tracks(alive_keys, frame_idx)
        self.cleanup_gallery_if_needed(frame_idx)

        return assignments

    def tick(self, frame_idx: int) -> None:
        """
        Tick nhẹ khi frame không có candidate.

        Hàm này không extract embedding; nó chỉ cleanup track/gallery theo thời gian.
        """
        self.cleanup_dead_tracks(set(), frame_idx)
        self.cleanup_gallery_if_needed(frame_idx)

    def get_track_state(self, key: ReIdTrackKey) -> ReIdTrackState | None:
        """Lấy state của một track nếu còn active."""
        return self.active_tracks.get(key)

    def _process_candidate(
        self,
        frame: np.ndarray,
        candidate: ReIdCandidate,
        frame_idx: int,
        current_bboxes: dict[ReIdTrackKey, BBoxXYXY],
    ) -> ReIdAssignment:
        """Cập nhật một candidate và trả assignment hiện tại của nó."""
        track = self._get_or_create_track(candidate, frame_idx)
        track.frame_count += 1
        track.last_seen = frame_idx
        track.bbox = candidate.bbox
        track.confidence = float(candidate.confidence)
        track.add_bbox(
            bbox=candidate.bbox,
            max_history=self.config.stable_bbox_window
        )

        crop = self._crop(frame, candidate.bbox)
        if crop.size == 0:
            return self._assignment_from_track(candidate, track)

        if not self._is_bbox_quality(
            track,
            candidate.bbox,
            candidate.confidence,
            frame.shape,
            current_bboxes,
            crop,
        ):
            return self._assignment_from_track(candidate, track)

        embedding = normalize_embedding(self.embedding_function(crop))
        track.add_embedding(embedding, frame_idx, self.config.max_buffer_size)

        if track.status in (ReIdTrackStatus.NEW, ReIdTrackStatus.UNCERTAIN):
            self._try_confirm(track, frame_idx)
        elif track.status == ReIdTrackStatus.CONFIRMED:
            self._reverify_confirmed_track(track, embedding, frame_idx)

        return self._assignment_from_track(candidate, track)

    def _get_or_create_track(
        self,
        candidate: ReIdCandidate,
        frame_idx: int,
    ) -> ReIdTrackState:
        """Lấy hoặc tạo track state theo `(camera_id, track_id)`."""
        if candidate.key not in self.active_tracks:
            self.active_tracks[candidate.key] = ReIdTrackState(
                key=candidate.key,
                last_seen=frame_idx,
            )

        return self.active_tracks[candidate.key]

    def _is_bbox_quality(
        self,
        track: ReIdTrackState,
        bbox: BBoxXYXY,
        confidence: float,
        frame_shape: tuple,
        current_bboxes: dict[ReIdTrackKey, BBoxXYXY],
        crop: np.ndarray,
    ) -> bool:
        """Kiểm tra bbox/crop có đủ tốt để extract embedding hay không."""
        if not self._is_bbox_geometry_quality(bbox, confidence, frame_shape):
            return False
        if self._is_near_frame_edge(bbox, frame_shape):
            return False
        if self._has_blocking_overlap(track.key, bbox, current_bboxes):
            return False
        if not self._is_bbox_stable(track):
            return False

        return self._is_crop_sharp(crop)

    def _is_bbox_geometry_quality(
        self,
        bbox: BBoxXYXY,
        confidence: float,
        frame_shape: tuple,
    ) -> bool:
        """Lọc nhanh bbox quá nhỏ, confidence thấp hoặc tỉ lệ quá dị."""
        x1, y1, x2, y2 = bbox
        width = x2 - x1
        height = y2 - y1
        frame_height, frame_width = frame_shape[:2]

        if confidence < self.config.min_detection_conf:
            return False
        if width < self.config.min_bbox_width or height < self.config.min_bbox_height:
            return False
        if height <= 0:
            return False

        aspect_ratio = width / height
        if not (
            self.config.min_bbox_aspect_ratio
            <= aspect_ratio
            <= self.config.max_bbox_aspect_ratio
        ):
            return False

        if x2 <= 0 or y2 <= 0 or x1 >= frame_width or y1 >= frame_height:
            return False

        return True

    def _is_near_frame_edge(self, bbox: BBoxXYXY, frame_shape: tuple) -> bool:
        """Bỏ người quá sát mép vì crop thường bị cụt thân."""
        x1, y1, x2, y2 = bbox
        frame_height, frame_width = frame_shape[:2]
        margin_x = frame_width * self.config.edge_margin_ratio
        margin_y = frame_height * self.config.edge_margin_ratio

        return (
            x1 < margin_x
            or y1 < margin_y
            or x2 > frame_width - margin_x
            or y2 > frame_height - margin_y
        )

    def _has_blocking_overlap(
        self,
        track_key: ReIdTrackKey,
        bbox: BBoxXYXY,
        current_bboxes: dict[ReIdTrackKey, BBoxXYXY],
    ) -> bool:
        """Bỏ bbox đang đè lên bbox người khác trong cùng frame/camera."""
        for other_key, other_bbox in current_bboxes.items():
            if other_key == track_key:
                continue
            if other_key.camera_id != track_key.camera_id:
                continue

            iou, ioa = self._bbox_overlap_scores(bbox, other_bbox)
            if (
                iou >= self.config.overlap_iou_threshold
                or ioa >= self.config.overlap_ioa_threshold
            ):
                return True

        return False

    def _is_bbox_stable(self, track: ReIdTrackState) -> bool:
        """Chỉ nhận embedding khi bbox ổn định trong vài frame gần nhất."""
        history = track.bbox_history
        if len(history) < self.config.stable_bbox_window:
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
        if max_center_shift > self.config.stable_center_shift_ratio:
            return False

        areas = widths * heights
        mean_area = float(np.mean(areas))
        if mean_area <= 1e-6:
            return False

        size_change = float(np.std(areas) / mean_area)
        return size_change <= self.config.stable_size_change_ratio

    def _is_crop_sharp(self, crop: np.ndarray) -> bool:
        """Dùng Laplacian variance để bỏ crop bị mờ/rung."""
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        return sharpness >= self.config.laplacian_var_threshold

    def _try_confirm(self, track: ReIdTrackState, frame_idx: int) -> None:
        """Nếu track có đủ embedding tốt, gán hoặc tạo global_id trong gallery."""
        if track.good_frame_count < self.config.buffer_min:
            return

        track.status = ReIdTrackStatus.PENDING
        create_on_uncertain = len(track.embedding_buffer) >= self.config.max_buffer_size
        result = self.gallery.resolve_identity(
            track.mean_embedding(),
            frame_idx,
            create_on_uncertain=create_on_uncertain,
        )
        # Nếu gallery tạo global_id mới thì chưa có profile cũ để so thật sự.
        # Không giữ best_similarity=0.0 lên label, tránh hiểu nhầm thành match kém.
        track.similarity = None if result.status == "new" else result.similarity

        if result.status == "uncertain":
            track.status = ReIdTrackStatus.UNCERTAIN
            return

        if result.global_id is None:
            raise RuntimeError("IdentityGallery resolved identity without a global_id")

        track.global_id = result.global_id
        track.status = ReIdTrackStatus.CONFIRMED
        track.confirmed_at = frame_idx
        track.reverify_miss_count = 0
        track.last_verified_similarity = track.similarity
        self._total_confirmed += 1

        LOGGER.info(
            "ReID confirmed track=%s/%s -> global_id=%s status=%s similarity=%s",
            track.key.camera_id,
            track.key.track_id,
            result.global_id,
            result.status,
            _format_similarity(track.similarity),
        )

    def _reverify_confirmed_track(
        self,
        track: ReIdTrackState,
        embedding: np.ndarray,
        frame_idx: int,
    ) -> None:
        """
        Xác minh lại confirmed track trước khi giữ global_id hoặc update EMA.

        ByteTrack có thể bị hoán đổi id khi hai người đi sát nhau. Vì vậy crop
        mới của một confirmed track phải còn giống profile global_id hiện tại.
        """
        if track.global_id is None:
            self._detach_track_identity(track, None, "confirmed track missing global_id")
            return

        similarity = self.gallery.similarity_to_profile(track.global_id, embedding)
        track.last_verified_similarity = similarity
        track.similarity = similarity

        if similarity is None:
            self._detach_track_identity(track, None, "global_id profile missing")
            return

        if similarity >= self.config.sim_threshold_match:
            track.status = ReIdTrackStatus.CONFIRMED
            track.reverify_miss_count = 0
            self._maybe_refresh_gallery(track, embedding, frame_idx)
            return

        self._handle_reverify_mismatch(track, similarity)

    def _handle_reverify_mismatch(
        self,
        track: ReIdTrackState,
        similarity: float,
    ) -> None:
        """Xử lý crop mới không còn đủ giống global_id đã confirm."""
        track.embedding_buffer.clear()
        track.good_frame_count = 0
        track.reverify_miss_count += 1

        if (
            similarity < self.config.sim_threshold_unsure
            or track.reverify_miss_count >= max(1, self.config.max_reverify_misses)
        ):
            self._detach_track_identity(track, similarity, "reverify mismatch")
            return

        track.status = ReIdTrackStatus.UNCERTAIN
        LOGGER.info(
            "ReID track=%s/%s marked uncertain for global_id=%s, similarity=%s",
            track.key.camera_id,
            track.key.track_id,
            track.global_id,
            _format_similarity(similarity),
        )

    def _detach_track_identity(
        self,
        track: ReIdTrackState,
        similarity: float | None,
        reason: str,
    ) -> None:
        """Tách global_id khỏi track khi nghi ByteTrack đã bị ID switch."""
        old_global_id = track.global_id
        track.global_id = None
        track.status = ReIdTrackStatus.NEW
        track.similarity = None
        track.confirmed_at = 0
        track.reverify_miss_count = 0
        track.embedding_buffer.clear()
        track.good_frame_count = 0

        LOGGER.warning(
            "ReID detached track=%s/%s from global_id=%s, similarity=%s, reason=%s",
            track.key.camera_id,
            track.key.track_id,
            old_global_id,
            _format_similarity(similarity),
            reason,
        )

    def _maybe_refresh_gallery(
        self,
        track: ReIdTrackState,
        embedding: np.ndarray,
        frame_idx: int,
    ) -> None:
        """Cập nhật embedding đại diện của global_id theo chu kỳ."""
        frames_since = track.frames_since_confirmed(frame_idx)
        if frames_since <= 0 or frames_since % self.config.update_interval != 0:
            return
        if track.global_id is None:
            return

        self.gallery.update_profile(track.global_id, embedding, frame_idx)

    def cleanup_dead_tracks(self, alive_keys: set[ReIdTrackKey], frame_idx: int) -> None:
        """Xóa track tạm đã mất dấu quá lâu khỏi bộ nhớ active."""
        dead_keys = [
            key
            for key, track in self.active_tracks.items()
            if key not in alive_keys and frame_idx - track.last_seen > self.config.grace_period
        ]

        for key in dead_keys:
            LOGGER.debug(
                "ReID removed track=%s/%s global_id=%s",
                key.camera_id,
                key.track_id,
                self.active_tracks[key].global_id,
            )
            del self.active_tracks[key]

    def cleanup_gallery_if_needed(self, frame_idx: int) -> None:
        """Dọn gallery định kỳ."""
        interval = self.config.gallery_cleanup_interval
        if interval > 0 and frame_idx > 0 and frame_idx % interval == 0:
            self.gallery.cleanup_old_profiles(frame_idx)

    def _assignment_from_track(
        self,
        candidate: ReIdCandidate,
        track: ReIdTrackState,
    ) -> ReIdAssignment:
        """Tạo assignment từ state hiện tại của track."""
        return ReIdAssignment(
            camera_id=candidate.camera_id,
            track_id=candidate.track_id,
            detection_index=candidate.detection_index,
            global_id=track.global_id,
            similarity=track.similarity,
            status=track.status,
        )

    @staticmethod
    def _crop(frame: np.ndarray, bbox: BBoxXYXY) -> np.ndarray:
        """Crop bbox và clamp tọa độ để không vượt biên ảnh."""
        x1, y1, x2, y2 = map(int, bbox)
        height, width = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(width, x2), min(height, y2)

        return frame[y1:y2, x1:x2]

    @staticmethod
    def _bbox_overlap_scores(bbox_a: BBoxXYXY, bbox_b: BBoxXYXY) -> tuple[float, float]:
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

    def __repr__(self) -> str:
        confirmed = sum(1 for track in self.active_tracks.values() if track.is_confirmed())
        return (
            f"<ReIdTrackManager active={len(self.active_tracks)} "
            f"confirmed={confirmed} total_ever={self._total_confirmed}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
def _format_similarity(similarity: float | None) -> str:
    """Format similarity cho log, fallback '-' khi đó là identity mới."""
    if similarity is None:
        return "-"

    return f"{similarity:.3f}"
