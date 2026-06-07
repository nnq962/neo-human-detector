"""
Chọn detection nào được đưa vào ReID.

Runtime có thể chạy ByteTrack cho tất cả người, nhưng ReID chỉ nên extract
embedding cho các bbox có ích về nghiệp vụ, ví dụ bbox nằm trong zone.
"""

from __future__ import annotations

from typing import Optional, Sequence

from src.detection.detections import Detection
from src.reid.types import ReIdCandidate


# ─────────────────────────────────────────────────────────────────────────────
def select_reid_candidates(
    *,
    camera_id: str,
    detections: Sequence[Detection],
    zone_names: Sequence[Optional[str]],
    zone_only: bool = True,
) -> list[ReIdCandidate]:
    """
    Tạo candidate ReID từ detections.

    Nếu `zone_only=True`, chỉ detection có track_id và nằm trong zone mới được
    chọn để crop/extract embedding.
    """
    candidates: list[ReIdCandidate] = []

    for index, detection in enumerate(detections):
        if detection.track_id is None:
            continue

        zone_name = zone_names[index] if index < len(zone_names) else None
        if zone_only and zone_name is None:
            continue

        candidates.append(
            ReIdCandidate(
                camera_id       = str(camera_id),
                track_id        = int(detection.track_id),
                detection_index = index,
                bbox            = detection.bbox,
                confidence      = float(detection.confidence),
                zone_name       = zone_name,
            )
        )

    return candidates
