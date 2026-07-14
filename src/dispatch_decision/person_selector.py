"""Chọn người phù hợp trong zone để tầng decision xem xét phục vụ."""

from __future__ import annotations

from typing import Optional, Sequence

from src.detection import Detection
from src.zones_management import Zone


# ─────────────────────────────────────────────────────────────────────────────
def select_zone_person(
    zone: Zone,
    detections: Sequence[Detection],
    zone_names: Sequence[Optional[str]],
) -> Optional[Detection]:
    """
    Chọn người đã có global ID và độ tương đồng cao nhất trong một zone.

    ``detections`` và ``zone_names`` phải có cùng thứ tự: phần tử tại cùng một
    vị trí mô tả một detection và tên zone chứa detection đó. Những detection
    không thuộc zone hoặc chưa được ReID gán ``global_id`` sẽ bị bỏ qua.

    Khi nhiều người có cùng độ tương đồng, detection có confidence cao hơn sẽ
    được ưu tiên. ``similarity=None`` được xem là thấp hơn mọi giá trị hợp lệ.
    Trả ``None`` nếu zone không có người nào đã được định danh.
    """
    if len(detections) != len(zone_names):
        raise ValueError(
            "detections và zone_names phải có cùng số phần tử: "
            f"{len(detections)} != {len(zone_names)}"
        )

    candidates = (
        detection
        for detection, zone_name in zip(detections, zone_names)
        if zone_name == zone.name and detection.global_id is not None
    )

    return max(
        candidates,
        key=lambda detection: (
            detection.similarity
            if detection.similarity is not None
            else float("-inf"),
            detection.confidence,
        ),
        default=None,
    )
