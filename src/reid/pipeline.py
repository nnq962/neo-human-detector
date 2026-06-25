"""
Pipeline ReID cấp cao để runtime gọi như một stage enrichment.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Iterable, Sequence

import numpy as np

from src.detection.datatypes import Detection, InferenceFrame
from src.reid.gallery import IdentityGallery
from src.reid.track_manager import ReIdTrackManager
from src.reid.datatypes import ReIdAssignment, ReIdCandidate, ReIdConfig


EmbeddingFunction = Callable[[np.ndarray], np.ndarray]


# ─────────────────────────────────────────────────────────────────────────────
class ReIdPipeline:
    """
    Stage ReID dùng trong Runtime.

    API chính: `process()` — một lời gọi duy nhất nhận frame + detection_frame,
    trả InferenceFrame đã được enrich global_id.

    Pipeline giữ một IdentityGallery chung cho toàn runtime, nhờ vậy global_id có
    thể thống nhất giữa nhiều camera nếu embedding match.
    """

    def __init__(
        self,
        *,
        config: ReIdConfig | None = None,
        embedding_function: EmbeddingFunction,
        gallery: IdentityGallery | None = None,
        close_callback: Callable[[], None] | None = None,
    ):
        self.config = config or ReIdConfig()
        self.gallery = gallery or IdentityGallery(self.config)
        self._close_callback = close_callback
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
            return embedder.extract_embedding(crop, color_format="bgr").detach().cpu().numpy()

        return cls(
            config=config,
            embedding_function=embedding_function,
            close_callback=embedder.close,
        )

    def close(self) -> None:
        if self._close_callback is not None:
            self._close_callback()
            self._close_callback = None

    # ── primary API ───────────────────────────────────────────────────────────
    def process(
        self,
        *,
        camera_id: str,
        frame: np.ndarray | None,
        detection_frame: InferenceFrame,
        zone_names: list[str | None],
        frame_idx: int,
        allowed_zone_names: set[str] | None = None,
    ) -> InferenceFrame:
        """
        Chạy toàn bộ ReID stage cho một frame.

        Chọn candidate → extract embedding → match gallery → enrich detection_frame.
        Trả InferenceFrame mới với global_id / similarity / status đã được gắn.
        """
        # Chọn candidate đủ điều kiện để đưa vào ReID.
        candidates = _select_reid_candidates(
            camera_id=camera_id,
            detections=detection_frame.detections,
            zone_names=zone_names,
            zone_only=self.config.zone_only,
            allowed_zone_names=allowed_zone_names,
        )

        assignments = self.update(
            camera_id=camera_id,
            frame=frame,
            candidates=candidates,
            frame_idx=frame_idx,
        )
        return self.enrich_detection_frame(detection_frame, assignments)

    # ── lower-level API ───────────────────────────────────────────────────────
    def update(
        self,
        *,
        camera_id: str,
        frame: np.ndarray | None,
        candidates: list[ReIdCandidate],
        frame_idx: int,
    ) -> list[ReIdAssignment]:
        """
        Update ReID bằng candidate trong frame hiện tại.

        Nếu không có frame hoặc candidate rỗng thì chỉ tick cleanup nhẹ.
        """
        if frame is None or not candidates:
            self.manager.tick(camera_id, frame_idx)
            return []

        assignments_by_key = self.manager.update(camera_id, frame, candidates, frame_idx)
        return [
            assignments_by_key[candidate.key]
            for candidate in candidates
            if candidate.key in assignments_by_key
        ]

    def enrich_detection_frame(
        self,
        detection_frame: InferenceFrame,
        assignments: Iterable[ReIdAssignment],
    ) -> InferenceFrame:
        """Trả InferenceFrame mới với Detection đã được gắn thông tin ReID."""
        assignment_by_index = {a.detection_index: a for a in assignments}
        enriched = []

        for index, detection in enumerate(detection_frame.detections):
            assignment = assignment_by_index.get(index)
            if assignment is None:
                enriched.append(detection)
            else:
                enriched.append(
                    replace(
                        detection,
                        global_id=assignment.global_id,
                        similarity=assignment.similarity,
                        status=assignment.status.value,
                    )
                )

        return replace(detection_frame, detections=enriched)


# ─────────────────────────────────────────────────────────────────────────────
def _select_reid_candidates(
    *,
    camera_id: str,
    detections: Sequence[Detection],
    zone_names: Sequence[str | None],
    zone_only: bool = True,
    allowed_zone_names: set[str] | None = None,
) -> list[ReIdCandidate]:
    """
    Tạo candidate ReID từ detections.

    Nếu `zone_only=True`, chỉ detection có track_id và nằm trong zone mới được
    chọn để crop/extract embedding. Nếu `allowed_zone_names` được truyền vào,
    detection cũng phải thuộc một zone trong tập này.
    """
    candidates: list[ReIdCandidate] = []

    for index, detection in enumerate(detections):
        if detection.track_id is None:
            continue

        zone_name = zone_names[index] if index < len(zone_names) else None
        if zone_only and zone_name is None:
            continue

        if allowed_zone_names is not None and zone_name not in allowed_zone_names:
            continue

        candidates.append(
            ReIdCandidate(
                camera_id=str(camera_id),
                track_id=int(detection.track_id),
                detection_index=index,
                bbox=detection.bbox,
                confidence=float(detection.confidence),
                zone_name=zone_name,
            )
        )

    return candidates
