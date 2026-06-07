"""
Pipeline ReID cấp cao để runtime gọi như một stage enrichment.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from src.detection.detections import DetectionFrame
from src.reid.candidate_selector import select_reid_candidates
from src.reid.gallery import IdentityGallery
from src.reid.track_manager import ReIdTrackManager
from src.reid.types import ReIdAssignment, ReIdCandidate, ReIdConfig


EmbeddingFunction = Callable[[np.ndarray], np.ndarray]


# ─────────────────────────────────────────────────────────────────────────────
class ReIdPipeline:
    """
    Stage ReID dùng trong DetectRuntime.

    Pipeline giữ một IdentityGallery chung cho toàn runtime, nhờ vậy global_id có
    thể thống nhất giữa nhiều camera nếu embedding match.
    """

    def __init__(
        self,
        *,
        config: ReIdConfig | None = None,
        embedding_function: EmbeddingFunction,
        gallery: IdentityGallery | None = None,
    ):
        self.config = config or ReIdConfig()
        self.gallery = gallery or IdentityGallery(self.config)
        self.manager = ReIdTrackManager(
            gallery=self.gallery,
            embedding_function=embedding_function,
            config=self.config,
        )

    @classmethod
    def from_config(cls, config: ReIdConfig) -> "ReIdPipeline":
        """Khởi tạo pipeline đầy đủ từ config, bao gồm OSNet embedder."""
        from src.reid.embedder import OSNetPersonEmbedder

        embedder = OSNetPersonEmbedder(
            model_path=Path(config.model_path) if config.model_path else None,
            device=config.device,
            batch_size=config.embedding_batch_size,
        )

        def embedding_function(crop: np.ndarray) -> np.ndarray:
            embedding = embedder.extract_embedding(crop, color_format="bgr")
            return embedding.detach().cpu().numpy()

        return cls(config=config, embedding_function=embedding_function)

    def select_candidates(
        self,
        *,
        camera_id: str,
        detection_frame: DetectionFrame,
        zone_names: list[str | None],
    ) -> list[ReIdCandidate]:
        """Chọn candidate theo config hiện tại."""
        return select_reid_candidates(
            camera_id=camera_id,
            detections=detection_frame.detections,
            zone_names=zone_names,
            zone_only=self.config.zone_only,
        )

    def update(
        self,
        *,
        frame: np.ndarray | None,
        candidates: list[ReIdCandidate],
        frame_idx: int,
    ) -> list[ReIdAssignment]:
        """
        Update ReID bằng candidate trong frame hiện tại.

        Nếu không có frame hoặc candidate rỗng thì chỉ tick cleanup nhẹ.
        """
        if frame is None or not candidates:
            self.manager.tick(frame_idx)
            return []

        assignments_by_key = self.manager.update(frame, candidates, frame_idx)
        assignments: list[ReIdAssignment] = []

        for candidate in candidates:
            assignment = assignments_by_key.get(candidate.key)
            if assignment is not None:
                assignments.append(assignment)

        return assignments

    def enrich_detection_frame(
        self,
        detection_frame: DetectionFrame,
        assignments: Iterable[ReIdAssignment],
    ) -> DetectionFrame:
        """Trả DetectionFrame mới với Detection đã được gắn thông tin ReID."""
        assignment_by_index = {
            assignment.detection_index: assignment
            for assignment in assignments
        }
        enriched_detections = []

        for index, detection in enumerate(detection_frame.detections):
            assignment = assignment_by_index.get(index)
            if assignment is None:
                enriched_detections.append(detection)
                continue

            enriched_detections.append(
                replace(
                    detection,
                    global_id=assignment.global_id,
                    similarity=assignment.similarity,
                    status=assignment.status.value,
                )
            )

        return replace(detection_frame, detections=enriched_detections)
