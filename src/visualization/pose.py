"""
Vẽ pose keypoints và skeleton theo chuẩn COCO 17 keypoints.

Input keypoints có thể là:
- np.ndarray shape (17, 2)  → tọa độ (x, y) pixel
- np.ndarray shape (17, 3)  → (x, y, confidence)

Skeleton được tô màu theo bên trái / phải / trục giữa cơ thể người.
"""

from __future__ import annotations

from typing import Optional, Sequence

import cv2
import numpy as np

from src.visualization.utils import get_draw_scale, scale_int
from src.visualization.colors import (
    POSE_CENTER_COLOR,
    POSE_KP_BORDER,
    POSE_KP_COLOR,
    POSE_LEFT_COLOR,
    POSE_RIGHT_COLOR,
)


# ─── COCO 17-keypoint definitions ─────────────────────────────────────────────
COCO_KEYPOINT_NAMES: list[str] = [
    "nose",           # 0
    "left_eye",       # 1
    "right_eye",      # 2
    "left_ear",       # 3
    "right_ear",      # 4
    "left_shoulder",  # 5
    "right_shoulder", # 6
    "left_elbow",     # 7
    "right_elbow",    # 8
    "left_wrist",     # 9
    "right_wrist",    # 10
    "left_hip",       # 11
    "right_hip",      # 12
    "left_knee",      # 13
    "right_knee",     # 14
    "left_ankle",     # 15
    "right_ankle",    # 16
]

# (kp_a, kp_b, side) — side xác định màu đường nối
# "left"/"right" theo góc nhìn của NGƯỜI (không phải người xem).
COCO_SKELETON: list[tuple[int, int, str]] = [
    (0,  1,  "right"),   # nose → left_eye
    (0,  2,  "left"),    # nose → right_eye
    (1,  3,  "right"),   # left_eye → left_ear
    (2,  4,  "left"),    # right_eye → right_ear
    (5,  6,  "center"),  # left_shoulder → right_shoulder
    (5,  7,  "right"),   # left_shoulder → left_elbow
    (7,  9,  "right"),   # left_elbow → left_wrist
    (6,  8,  "left"),    # right_shoulder → right_elbow
    (8,  10, "left"),    # right_elbow → right_wrist
    (5,  11, "right"),   # left_shoulder → left_hip
    (6,  12, "left"),    # right_shoulder → right_hip
    (11, 12, "center"),  # left_hip → right_hip
    (11, 13, "right"),   # left_hip → left_knee
    (13, 15, "right"),   # left_knee → left_ankle
    (12, 14, "left"),    # right_hip → right_knee
    (14, 16, "left"),    # right_knee → right_ankle
]

_SIDE_COLOR = {
    "left"  : POSE_LEFT_COLOR,
    "right" : POSE_RIGHT_COLOR,
    "center": POSE_CENTER_COLOR,
}

# Indices 0–4: nose, left_eye, right_eye, left_ear, right_ear
_HEAD_KP_INDICES: frozenset[int] = frozenset({0, 1, 2, 3, 4})


# ─────────────────────────────────────────────────────────────────────────────
def draw_pose(
    frame           : np.ndarray,
    keypoints       : np.ndarray,
    confidences     : Optional[np.ndarray] = None,
    *,
    conf_threshold  : float = 0.3,
    color_by_side   : bool  = True,
    draw_head_kps   : bool  = True,
) -> None:
    """
    Vẽ skeleton + keypoint circles cho một người.

    Args:
        frame:          Frame BGR để vẽ lên (in-place).
        keypoints:      np.ndarray shape (17, 2) pixel (x, y)
                        hoặc (17, 3) nếu confidence đã nằm trong cột thứ 3.
        confidences:    np.ndarray shape (17,) confidence mỗi keypoint.
                        Nếu None và keypoints.shape[-1] == 3 thì tự lấy từ cột thứ 3.
        conf_threshold: Keypoint dưới ngưỡng này bị bỏ qua khi vẽ.
        color_by_side:  True → tô màu skeleton theo trái/phải/trục.
        draw_head_kps:  False → bỏ qua nose, eyes, ears (indices 0–4).
    """
    kps, confs = _parse_keypoints(keypoints, confidences)
    scale     = get_draw_scale(frame)
    bone_w    = scale_int(3, scale)
    kp_radius = scale_int(5, scale)
    kp_border = scale_int(2, scale)

    # Skeleton lines
    for kp_a, kp_b, side in COCO_SKELETON:
        if not draw_head_kps and (kp_a in _HEAD_KP_INDICES or kp_b in _HEAD_KP_INDICES):
            continue
        if confs[kp_a] < conf_threshold or confs[kp_b] < conf_threshold:
            continue
        pt_a = (int(kps[kp_a, 0]), int(kps[kp_a, 1]))
        pt_b = (int(kps[kp_b, 0]), int(kps[kp_b, 1]))
        color = _SIDE_COLOR[side] if color_by_side else POSE_CENTER_COLOR
        cv2.line(frame, pt_a, pt_b, color, bone_w, cv2.LINE_AA)

    # Keypoint circles (17 điểm COCO)
    for i, (x, y) in enumerate(kps):
        if not draw_head_kps and i in _HEAD_KP_INDICES:
            continue
        if confs[i] < conf_threshold:
            continue
        _draw_kp_dot(frame, int(x), int(y), kp_radius, kp_border)

    # Điểm hip center: trung điểm left_hip (11) và right_hip (12)
    _draw_hip_center(frame, kps, confs, conf_threshold, kp_radius, kp_border)


# ─────────────────────────────────────────────────────────────────────────────
def draw_poses(
    frame       : np.ndarray,
    keypoints   : Sequence[np.ndarray],
    confidences : Optional[Sequence[Optional[np.ndarray]]] = None,
    *,
    conf_threshold: float = 0.3,
    color_by_side : bool  = True,
    draw_head_kps : bool  = True,
) -> None:
    """Vẽ pose cho nhiều người trong cùng một frame."""
    for i, kps in enumerate(keypoints):
        confs_i = confidences[i] if confidences is not None else None
        draw_pose(
            frame,
            kps,
            confs_i,
            conf_threshold=conf_threshold,
            color_by_side=color_by_side,
            draw_head_kps=draw_head_kps,
        )


# ─────────────────────────────────────────────────────────────────────────────
def keypoints_from_yolo(result) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """
    Trích keypoints và confidences từ YOLO pose result.

    Returns:
        (list_of_kps, list_of_confs)
        Mỗi phần tử tương ứng một người được detect:
        - kps:   np.ndarray shape (17, 2) pixel (x, y)
        - confs: np.ndarray shape (17,) confidence
    """
    kp_data = getattr(result, "keypoints", None)
    if kp_data is None:
        return [], []

    xy   = kp_data.xy.cpu().numpy()    # (N, 17, 2)
    conf = kp_data.conf.cpu().numpy()  # (N, 17)

    kps_list   = [xy[i]   for i in range(len(xy))]
    confs_list = [conf[i] for i in range(len(conf))]
    return kps_list, confs_list


# ─────────────────────────────────────────────────────────────────────────────
def _parse_keypoints(
    keypoints  : np.ndarray,
    confidences: Optional[np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    """Chuẩn hóa keypoints về (17, 2) và confidences về (17,)."""
    kps = np.asarray(keypoints, dtype=np.float32)

    if kps.ndim != 2 or kps.shape[0] != 17:
        raise ValueError(
            f"keypoints phải có shape (17, 2) hoặc (17, 3), nhận {kps.shape}."
        )

    if kps.shape[1] == 3 and confidences is None:
        # Confidence nằm ở cột thứ 3
        confs = kps[:, 2]
        kps   = kps[:, :2]
    elif kps.shape[1] == 2:
        confs = (
            np.asarray(confidences, dtype=np.float32)
            if confidences is not None
            else np.ones(17, dtype=np.float32)
        )
    else:
        raise ValueError(
            f"keypoints phải có 2 hoặc 3 cột, nhận {kps.shape[1]}."
        )

    return kps, confs


def _draw_kp_dot(
    frame    : np.ndarray,
    x        : int,
    y        : int,
    radius   : int,
    border   : int,
) -> None:
    cv2.circle(frame, (x, y), radius + border, POSE_KP_BORDER, -1, cv2.LINE_AA)
    cv2.circle(frame, (x, y), radius,          POSE_KP_COLOR,  -1, cv2.LINE_AA)


def _draw_hip_center(
    frame         : np.ndarray,
    kps           : np.ndarray,
    confs         : np.ndarray,
    conf_threshold: float,
    kp_radius     : int,
    kp_border     : int,
) -> None:
    """Vẽ trung điểm của left_hip (11) và right_hip (12)."""
    if confs[11] < conf_threshold or confs[12] < conf_threshold:
        return
    cx = int((kps[11, 0] + kps[12, 0]) / 2)
    cy = int((kps[11, 1] + kps[12, 1]) / 2)
    _draw_kp_dot(frame, cx, cy, kp_radius, kp_border)
