"""
Lọc chất lượng crop người trước khi extract ReID embedding.

Tách riêng khỏi track_manager để logic track và logic filter không trộn vào nhau.
"""

from __future__ import annotations

import cv2
import numpy as np

from src.reid.datatypes import BBoxXYXY, ReIdConfig, ReIdTrackKey, ReIdTrackState


# ─────────────────────────────────────────────────────────────────────────────
class CropQualityFilter:
    """Kiểm tra bbox / crop có đủ sạch để extract embedding."""

    def __init__(self, config: ReIdConfig):
        self.config = config

    def is_quality(
        self,
        track: ReIdTrackState,
        bbox: BBoxXYXY,
        frame_shape: tuple,
        current_bboxes: dict[ReIdTrackKey, BBoxXYXY],
        crop: np.ndarray,
    ) -> bool:
        if not self._is_geometry_ok(bbox, frame_shape):
            return False
        if self._has_overlap(track.key, bbox, current_bboxes):
            return False
        if not self._is_stable(track):
            return False
        return self._is_sharp(crop)

    def _is_geometry_ok(
        self,
        bbox: BBoxXYXY,
        frame_shape: tuple,
    ) -> bool:
        x1, y1, x2, y2 = bbox
        frame_height, frame_width = frame_shape[:2]

        if x2 <= 0 or y2 <= 0 or x1 >= frame_width or y1 >= frame_height:
            return False

        return True

    def _has_overlap(
        self,
        track_key: ReIdTrackKey,
        bbox: BBoxXYXY,
        current_bboxes: dict[ReIdTrackKey, BBoxXYXY],
    ) -> bool:
        for other_key, other_bbox in current_bboxes.items():
            if other_key == track_key or other_key.camera_id != track_key.camera_id:
                continue
            iou, ioa = _overlap_scores(bbox, other_bbox)
            if (
                iou >= self.config.overlap_iou_threshold
                or ioa >= self.config.overlap_ioa_threshold
            ):
                return True
        return False

    def _is_stable(self, track: ReIdTrackState) -> bool:
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
        if float(center_distances.max()) / avg_diag > self.config.stable_center_shift_ratio:
            return False

        areas = widths * heights
        mean_area = float(np.mean(areas))
        if mean_area <= 1e-6:
            return False

        return float(np.std(areas) / mean_area) <= self.config.stable_size_change_ratio

    def _is_sharp(self, crop: np.ndarray) -> bool:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var()) >= self.config.laplacian_var_threshold


# ─────────────────────────────────────────────────────────────────────────────
def _overlap_scores(bbox_a: BBoxXYXY, bbox_b: BBoxXYXY) -> tuple[float, float]:
    """Trả (IoU, IoA của bbox nhỏ hơn) giữa hai bbox."""
    ax1, ay1, ax2, ay2 = bbox_a
    bx1, by1, bx2, by2 = bbox_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    if area_a <= 0 or area_b <= 0 or inter_area <= 0:
        return 0.0, 0.0

    union = area_a + area_b - inter_area
    iou = inter_area / union if union > 0 else 0.0
    ioa = inter_area / min(area_a, area_b)
    return float(iou), float(ioa)
