"""
Identity gallery cho ReID.

Gallery là bộ nhớ global của cả runtime. Mọi camera cùng query vào gallery này,
vì vậy một người xuất hiện ở nhiều camera vẫn có cơ hội được resolve về cùng
`global_id` nếu embedding đủ giống.
"""

from __future__ import annotations

import time

import numpy as np

from src.reid.datatypes import IdentityMatchResult, IdentityProfile, ReIdConfig, ReIdTrackStatus
from src.reid.utils import cosine_similarity, normalize_embedding


from utils import LOGGER


# ─────────────────────────────────────────────────────────────────────────────
class IdentityGallery:
    """
    Lưu các global_id bền vững và resolve embedding mới thành danh tính.

    `global_id` là id xuyên camera trong một runtime session; nó độc lập với
    ByteTrack id tạm của từng stream.
    """

    def __init__(self, config: ReIdConfig | None = None):
        self.config = config or ReIdConfig()
        self._profiles: dict[int, IdentityProfile] = {}
        self._next_id = 1

    def resolve_identity(
        self,
        embedding: np.ndarray,
        frame_idx: int,
    ) -> IdentityMatchResult:
        """
        Resolve embedding trung bình của một track thành global_id.

        Nếu cosine similarity với profile tốt nhất đạt ngưỡng match, dùng lại
        global_id cũ và refresh metadata xuất hiện. Nếu không đạt ngưỡng, tạo
        profile/global_id mới và trả status NEW.
        """
        embedding = normalize_embedding(embedding)
        best_id, best_similarity = self._find_best_match(embedding)

        # Nếu embedding mới đủ giống profile cũ, refresh profile và trả MATCHED.
        if best_similarity >= self.config.sim_threshold_match:
            profile = self._profiles[best_id]
            profile.hit_count += 1
            profile.last_seen = frame_idx
            profile.last_seen_at = time.monotonic()
            return IdentityMatchResult(ReIdTrackStatus.MATCHED, best_id, best_similarity)

        # Nếu embedding mới không match với profile cũ, tạo profile mới và trả NEW.
        global_id = self._create_profile(embedding, frame_idx)
        return IdentityMatchResult(ReIdTrackStatus.NEW, global_id, best_similarity)

    def update_profile(
        self,
        global_id: int,
        embedding: np.ndarray,
        frame_idx: int,
    ) -> None:
        """Refresh embedding đại diện của global_id bằng EMA."""
        if global_id not in self._profiles:
            return

        embedding = normalize_embedding(embedding)
        profile = self._profiles[global_id]
        alpha = self.config.ema_alpha
        profile.embedding = alpha * profile.embedding + (1 - alpha) * embedding
        profile.embedding = normalize_embedding(profile.embedding)
        profile.last_seen = frame_idx
        profile.last_seen_at = time.monotonic()
        profile.samples.append(embedding.copy())

        if len(profile.samples) > self.config.max_samples:
            profile.samples.pop(0)

    def similarity_to_profile(self, global_id: int, embedding: np.ndarray) -> float | None:
        """Tính cosine giữa embedding mới và profile của một global_id cụ thể."""
        profile = self._profiles.get(global_id)
        if profile is None:
            return None

        return cosine_similarity(embedding, profile.embedding)

    def cleanup_old_profiles(self, _frame_idx: int | None = None) -> list[int]:
        """Xóa global_id quá lâu không xuất hiện để gallery không phình mãi."""
        now = time.monotonic()
        expired = [
            global_id
            for global_id, profile in self._profiles.items()
            if now - profile.last_seen_at > self.config.gallery_ttl_seconds
        ]

        for global_id in expired:
            del self._profiles[global_id]

        if expired:
            LOGGER.info("ReID gallery cleanup removed global_ids=%s", expired)

        return expired

    def merge_similar_profiles(self) -> list[tuple[int, int]]:
        """
        Gộp các profile quá giống nhau.

        Hàm này hữu ích khi runtime lỡ tạo hai global_id cho cùng một người.
        """
        ids = list(self._profiles.keys())
        merged_pairs: list[tuple[int, int]] = []
        to_delete: set[int] = set()

        for index, left_id in enumerate(ids):
            for right_id in ids[index + 1 :]:
                if left_id in to_delete or right_id in to_delete:
                    continue

                similarity = cosine_similarity(
                    self._profiles[left_id].embedding,
                    self._profiles[right_id].embedding,
                )
                if similarity < self.config.sim_threshold_match:
                    continue

                keep_id, drop_id = self._pick_merge_ids(left_id, right_id)
                to_delete.add(drop_id)
                merged_pairs.append((drop_id, keep_id))
                LOGGER.info(
                    "ReID gallery merge global_id %s -> %s, similarity=%.3f",
                    drop_id,
                    keep_id,
                    similarity,
                )

        for global_id in to_delete:
            del self._profiles[global_id]

        return merged_pairs

    def summary(self) -> dict[int, dict[str, int]]:
        """Trả summary nhỏ phục vụ debug/log."""
        return {
            global_id: {
                "hit_count": profile.hit_count,
                "last_seen": profile.last_seen,
            }
            for global_id, profile in self._profiles.items()
        }

    def _find_best_match(self, embedding: np.ndarray) -> tuple[int, float]:
        """Quét toàn bộ gallery và trả global_id có cosine cao nhất."""
        embedding = normalize_embedding(embedding)
        if not self._profiles:
            return -1, 0.0

        best_id = -1
        best_similarity = 0.0
        for global_id, profile in self._profiles.items():
            similarity = cosine_similarity(embedding, profile.embedding)
            if similarity > best_similarity:
                best_id = global_id
                best_similarity = similarity

        return best_id, best_similarity

    def _create_profile(self, embedding: np.ndarray, frame_idx: int) -> int:
        """Tạo global_id mới và lưu embedding đại diện ban đầu."""
        embedding = normalize_embedding(embedding)
        global_id = self._next_id
        self._next_id += 1
        self._profiles[global_id] = IdentityProfile(
            global_id=global_id,
            embedding=embedding.copy(),
            samples=[embedding.copy()],
            last_seen=frame_idx,
            last_seen_at=time.monotonic(),
            hit_count=1,
        )

        return global_id

    def _pick_merge_ids(self, left_id: int, right_id: int) -> tuple[int, int]:
        """Chọn profile giữ lại khi merge dựa trên hit_count."""
        left = self._profiles[left_id]
        right = self._profiles[right_id]

        if left.hit_count >= right.hit_count:
            return left_id, right_id

        return right_id, left_id

    def __repr__(self) -> str:
        return f"<IdentityGallery profiles={len(self._profiles)} next_id={self._next_id}>"
