from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Literal

import numpy as np

from src.reid_types import GalleryEntry, TrackerConfig
from src.reid_utils import cosine_similarity, normalize_embedding

logger = logging.getLogger(__name__)


GalleryQueryStatus = Literal["match", "uncertain", "new"]


@dataclass(frozen=True)
class GalleryQueryResult:
    """Kết quả query Gallery trước khi TrackManager quyết định confirm hay chờ."""

    status: GalleryQueryStatus
    global_id: int | None
    similarity: float


class Gallery:
    """
    Tầng 2 của pipeline ReID.

    Gallery lưu các global_id bền vững. Khi ByteTrack tạo track_id mới, TrackManager
    sẽ query vào đây để quyết định đó là người cũ quay lại hay người mới.
    """

    def __init__(self, config: TrackerConfig | None = None):
        self.cfg = config or TrackerConfig()
        self._entries: dict[int, GalleryEntry] = {}
        self._next_id: int = 1

    def query_or_create(self, embedding: np.ndarray, frame_idx: int) -> int:
        """
        Tìm global_id gần nhất bằng cosine similarity.

        Nếu similarity đủ cao thì trả về ID cũ, nếu không thì tạo global_id mới.
        """
        result = self.resolve_identity(
            embedding,
            frame_idx,
            create_on_uncertain=True,
        )
        if result.global_id is None:
            raise RuntimeError("Gallery query_or_create did not return a global_id")
        return result.global_id

    def resolve_identity(
        self,
        embedding: np.ndarray,
        frame_idx: int,
        *,
        create_on_uncertain: bool = False,
    ) -> GalleryQueryResult:
        """
        Query gallery với 3 vùng quyết định:

        - match: similarity >= sim_threshold_match, dùng global_id cũ.
        - uncertain: sim_threshold_unsure <= similarity < sim_threshold_match.
        - new: similarity < sim_threshold_unsure, tạo global_id mới.
        """
        embedding = normalize_embedding(embedding)
        best_id, best_sim = self._find_best_match(embedding)

        if best_sim >= self.cfg.sim_threshold_match:
            # Người cũ quay lại: chỉ cập nhật metadata, chưa EMA embedding ở đây.
            entry = self._entries[best_id]
            entry.hit_count += 1
            entry.last_seen = frame_idx
            entry.last_seen_at = time.monotonic()
            logger.debug("Gallery match: global_id=%s, sim=%.3f", best_id, best_sim)
            return GalleryQueryResult("match", best_id, best_sim)

        if (
            best_id != -1
            and best_sim >= self.cfg.sim_threshold_unsure
            and not create_on_uncertain
        ):
            # Vùng nhập nhằng: chưa tạo ID mới để tránh tách nhầm cùng một người.
            logger.debug(
                "Gallery uncertain: candidate_global_id=%s, sim=%.3f",
                best_id,
                best_sim,
            )
            return GalleryQueryResult("uncertain", best_id, best_sim)

        # Không có ai đủ giống trong gallery nên tạo danh tính mới.
        new_id = self._create_entry(embedding, frame_idx)
        logger.debug(
            "Gallery new entry: global_id=%s, best_sim_was=%.3f",
            new_id,
            best_sim,
        )
        return GalleryQueryResult("new", new_id, best_sim)

    def update_entry(
        self, global_id: int, new_embedding: np.ndarray, frame_idx: int
    ) -> None:
        """Refresh embedding đại diện của global_id bằng EMA."""
        if global_id not in self._entries:
            return

        new_embedding = normalize_embedding(new_embedding)
        entry = self._entries[global_id]
        alpha = self.cfg.ema_alpha
        # EMA giúp embedding đại diện thích nghi pose/ánh sáng nhưng không đổi quá gắt.
        entry.embedding = alpha * entry.embedding + (1 - alpha) * new_embedding
        entry.embedding = normalize_embedding(entry.embedding)
        entry.last_seen = frame_idx
        entry.last_seen_at = time.monotonic()

        # Giữ một ít sample gần nhất để debug hoặc mở rộng matching sau này.
        entry.samples.append(new_embedding.copy())
        if len(entry.samples) > self.cfg.max_samples:
            entry.samples.pop(0)

    def cleanup_old_entries(self, _frame_idx: int | None = None) -> list[int]:
        """Xóa global_id quá lâu không xuất hiện để gallery không phình mãi."""
        now = time.monotonic()
        ttl_seconds = self.cfg.gallery_ttl_seconds
        expired = [
            gid
            for gid, entry in self._entries.items()
            if (now - entry.last_seen_at) > ttl_seconds
        ]
        for gid in expired:
            del self._entries[gid]
        if expired:
            logger.info("Gallery cleanup: removed global_ids=%s", expired)
        return expired

    def merge_similar_entries(self) -> list[tuple[int, int]]:
        """
        Gộp các global_id quá giống nhau.

        Hàm này hữu ích khi hệ thống lỡ tạo 2 global_id cho cùng một người.
        """
        ids = list(self._entries.keys())
        merged_pairs: list[tuple[int, int]] = []
        to_delete: set[int] = set()

        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                if a in to_delete or b in to_delete:
                    continue

                sim = cosine_similarity(
                    self._entries[a].embedding,
                    self._entries[b].embedding,
                )
                if sim < self.cfg.sim_threshold_match:
                    continue

                keep, drop = (
                    (a, b)
                    if self._entries[a].hit_count >= self._entries[b].hit_count
                    else (b, a)
                )
                to_delete.add(drop)
                merged_pairs.append((drop, keep))
                logger.info("Gallery merge: %s -> %s, sim=%.3f", drop, keep, sim)

        for gid in to_delete:
            del self._entries[gid]

        return merged_pairs

    def _find_best_match(self, embedding: np.ndarray) -> tuple[int, float]:
        """Quét toàn bộ gallery và trả về global_id có cosine cao nhất."""
        embedding = normalize_embedding(embedding)
        if not self._entries:
            return -1, 0.0

        best_id, best_sim = -1, 0.0
        for gid, entry in self._entries.items():
            sim = cosine_similarity(embedding, entry.embedding)
            if sim > best_sim:
                best_sim = sim
                best_id = gid
        return best_id, best_sim

    def _create_entry(self, embedding: np.ndarray, frame_idx: int) -> int:
        """Tạo global_id mới và lưu embedding đại diện ban đầu."""
        embedding = normalize_embedding(embedding)
        gid = self._next_id
        self._next_id += 1
        self._entries[gid] = GalleryEntry(
            global_id=gid,
            embedding=embedding.copy(),
            samples=[embedding.copy()],
            last_seen=frame_idx,
            last_seen_at=time.monotonic(),
            hit_count=1,
        )
        return gid

    def __repr__(self) -> str:
        return f"<Gallery entries={len(self._entries)} next_id={self._next_id}>"

    def summary(self) -> dict:
        return {
            gid: {"hit_count": entry.hit_count, "last_seen": entry.last_seen}
            for gid, entry in self._entries.items()
        }
