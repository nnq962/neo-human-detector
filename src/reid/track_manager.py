"""
Track manager cho ReID online.

Manager nhận các candidate đã được runtime lọc theo zone, gom embedding cho từng
ByteTrack track tạm, rồi query IdentityGallery để đổi sang global_id bền vững.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from src.reid.crop_filter import CropQualityFilter
from src.reid.gallery import IdentityGallery
from src.reid.datatypes import (
    BBoxXYXY,
    ReIdAssignment,
    ReIdCandidate,
    ReIdConfig,
    ReIdTrackKey,
    ReIdTrackState,
    ReIdTrackStatus,
)
from src.reid.utils import normalize_embedding, crop, fmt_sim


from utils import LOGGER
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
        # Bộ nhớ tạm của ReID cho các ByteTrack track đang còn được hệ thống theo dõi gần đây.
        self.active_tracks: dict[ReIdTrackKey, ReIdTrackState] = {}
        self._quality_filter = CropQualityFilter(self.config)
        self._total_confirmed = 0

    def update(
        self,
        camera_id: str,
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
        current_bboxes = {candidate.key: candidate.bbox for candidate in candidates}
        assignments: dict[ReIdTrackKey, ReIdAssignment] = {}

        for candidate in candidates:
            assignments[candidate.key] = self._process_candidate(
                frame, candidate, frame_idx, current_bboxes,
            )

        self.cleanup_dead_tracks(camera_id, alive_keys, frame_idx)
        self.cleanup_gallery_if_needed(frame_idx)

        return assignments

    def tick(self, camera_id: str, frame_idx: int) -> None:
        """
        Tick nhẹ khi frame không có candidate.

        Không extract embedding; chỉ cleanup track/gallery theo thời gian.
        """
        self.cleanup_dead_tracks(camera_id, set(), frame_idx)
        self.cleanup_gallery_if_needed(frame_idx)

    def get_track_state(self, key: ReIdTrackKey) -> ReIdTrackState | None:
        return self.active_tracks.get(key)

    def _process_candidate(
        self,
        frame: np.ndarray,
        candidate: ReIdCandidate,
        frame_idx: int,
        current_bboxes: dict[ReIdTrackKey, BBoxXYXY],
    ) -> ReIdAssignment:
        track = self._get_or_create_track(candidate, frame_idx)
        track.frame_count += 1
        track.last_seen = frame_idx
        track.bbox = candidate.bbox
        track.confidence = float(candidate.confidence)
        track.add_bbox(bbox=candidate.bbox, max_history=self.config.stable_bbox_window)

        person_crop = crop(frame, candidate.bbox)
        if person_crop.size == 0:
            return self._assignment_from(candidate, track)

        if not self._quality_filter.is_quality(
            track, candidate.bbox,
            frame.shape, current_bboxes, person_crop,
        ):
            return self._assignment_from(candidate, track)

        embedding = normalize_embedding(self.embedding_function(person_crop))
        track.add_embedding(embedding, frame_idx, self.config.max_buffer_size)

        if track.status == ReIdTrackStatus.NEW:
            self._try_confirm(track, frame_idx)
        elif track.status == ReIdTrackStatus.MATCHED:
            self._reverify_confirmed_track(track, embedding, frame_idx)

        return self._assignment_from(candidate, track)

    def _get_or_create_track(
        self,
        candidate: ReIdCandidate,
        frame_idx: int,
    ) -> ReIdTrackState:
        if candidate.key not in self.active_tracks:
            self.active_tracks[candidate.key] = ReIdTrackState(
                key=candidate.key,
                last_seen=frame_idx,
            )
        return self.active_tracks[candidate.key]

    def _try_confirm(self, track: ReIdTrackState, frame_idx: int) -> None:
        """Nếu track có đủ embedding tốt, gán hoặc tạo global_id trong gallery."""
        # Nếu track chưa đủ embedding tốt thì không làm gì cả, chờ thêm frame.
        if track.good_frame_count < self.config.buffer_min:
            return

        result = self.gallery.resolve_identity(track.mean_embedding(), frame_idx)
        if result.global_id is None:
            raise RuntimeError("IdentityGallery resolved identity without a global_id")

        track.global_id = result.global_id
        track.similarity = None if result.status == ReIdTrackStatus.NEW else result.similarity
        track.status = ReIdTrackStatus.MATCHED
        track.matched_at = frame_idx
        track.reverify_miss_count = 0
        self._total_confirmed += 1

        LOGGER.info(
            "ReID confirmed track=%s/%s -> global_id=%s status=%s similarity=%s",
            track.key.camera_id,
            track.key.track_id,
            result.global_id,
            result.status,
            fmt_sim(track.similarity),
        )

    def _reverify_confirmed_track(
        self,
        track: ReIdTrackState,
        embedding: np.ndarray,
        frame_idx: int,
    ) -> None:
        """
        Xác minh lại confirmed track.

        ByteTrack có thể bị hoán đổi id khi hai người đi sát nhau. Crop mới không
        còn khớp profile thì tách global_id ngay lập tức, không giữ trạng thái trung gian.
        """
        # Nếu track chưa có global_id thì không thể xác minh, tách track ra khỏi gallery.
        if track.global_id is None:
            self._detach_identity(track, None, "confirmed track missing global_id")
            return

        similarity = self.gallery.similarity_to_profile(track.global_id, embedding)
        track.similarity = similarity

        if similarity is None:
            self._detach_identity(track, None, "global_id profile missing")
            return

        # Update EMA profile trong gallery nếu embedding mới vẫn khớp tốt với profile cũ.
        if similarity >= self.config.sim_threshold_match:
            track.reverify_miss_count = 0
            self._maybe_refresh_gallery(track, embedding, frame_idx)
            return

        track.reverify_miss_count += 1
        if track.reverify_miss_count < self.config.max_reverify_misses:
            LOGGER.debug(
                "ReID reverify miss track=%s/%s global_id=%s similarity=%s miss=%d/%d",
                track.key.camera_id,
                track.key.track_id,
                track.global_id,
                fmt_sim(similarity),
                track.reverify_miss_count,
                self.config.max_reverify_misses,
            )
            return

        self._detach_identity(
            track,
            similarity,
            f"reverify mismatch {track.reverify_miss_count}/{self.config.max_reverify_misses}",
        )

    def _detach_identity(
        self,
        track: ReIdTrackState,
        similarity: float | None,
        reason: str,
    ) -> None:
        """Gỡ global identity khỏi track khi nghi ByteTrack đã bị ID switch."""
        old_global_id = track.global_id
        track.global_id = None
        track.status = ReIdTrackStatus.NEW
        track.similarity = None
        track.matched_at = 0
        track.embedding_buffer.clear()
        track.good_frame_count = 0
        track.reverify_miss_count = 0

        LOGGER.warning(
            "ReID detached track=%s/%s from global_id=%s, similarity=%s, reason=%s",
            track.key.camera_id,
            track.key.track_id,
            old_global_id,
            fmt_sim(similarity),
            reason,
        )

    def _maybe_refresh_gallery(
        self,
        track: ReIdTrackState,
        embedding: np.ndarray,
        frame_idx: int,
    ) -> None:
        """Cập nhật profile gallery theo chu kỳ cho track đã match ổn định.

        Không refresh mỗi frame để tránh profile bị trôi theo crop nhiễu; chỉ
        update EMA sau mỗi `update_interval` frame kể từ lúc track được match.
        """
        frames_since = track.frames_since_matched(frame_idx)
        if frames_since <= 0 or frames_since % self.config.update_interval != 0:
            return
        if track.global_id is None:
            return
        self.gallery.update_profile(track.global_id, embedding, frame_idx)

    def cleanup_dead_tracks(
        self,
        camera_id: str,
        alive_keys: set[ReIdTrackKey],
        frame_idx: int,
    ) -> None:
        """Xóa track tạm của đúng camera hiện tại sau `grace_period` frame."""
        dead_keys = [
            key
            for key, track in self.active_tracks.items()
            if key.camera_id == camera_id
            and key not in alive_keys
            and frame_idx - track.last_seen > self.config.grace_period
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
        """Dọn gallery định kỳ để xóa các global_id quá lâu không gặp lại."""
        interval = self.config.gallery_cleanup_interval
        if interval > 0 and frame_idx > 0 and frame_idx % interval == 0:
            self.gallery.cleanup_old_profiles(frame_idx)

    def _assignment_from(
        self,
        candidate: ReIdCandidate,
        track: ReIdTrackState,
    ) -> ReIdAssignment:
        return ReIdAssignment(
            camera_id=candidate.camera_id,
            track_id=candidate.track_id,
            detection_index=candidate.detection_index,
            global_id=track.global_id,
            similarity=track.similarity,
            status=track.status,
        )

    def __repr__(self) -> str:
        confirmed = sum(1 for t in self.active_tracks.values() if t.is_matched())
        return (
            f"<ReIdTrackManager active={len(self.active_tracks)} "
            f"confirmed={confirmed} total_ever={self._total_confirmed}>"
        )
