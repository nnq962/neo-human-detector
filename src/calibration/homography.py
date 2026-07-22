"""Tính và đánh giá Homography từ pixel camera sang tọa độ thực."""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np


DEFAULT_RANSAC_THRESHOLD_METERS = 0.10
MIN_POINT_COUNT = 4


# ─────────────────────────────────────────────────────────────────────────────
def calculate_homography(
    pixel_points: Sequence[Sequence[float]],
    world_points: Sequence[Sequence[float]],
    *,
    point_ids: Sequence[str] | None = None,
    ransac_threshold_m: float = DEFAULT_RANSAC_THRESHOLD_METERS,
) -> dict:
    """Tính H ánh xạ ``pixel -> world`` và sai số chiếu lại theo mét."""
    pixels = _as_point_array(pixel_points, name="Pixel points")
    worlds = _as_point_array(world_points, name="World points")

    if len(pixels) != len(worlds):
        raise ValueError("Số pixel point và world point phải bằng nhau.")
    if len(pixels) < MIN_POINT_COUNT:
        raise ValueError("Cần ít nhất 4 điểm để tính ma trận H.")
    if not np.isfinite(ransac_threshold_m) or ransac_threshold_m <= 0:
        raise ValueError("Ngưỡng RANSAC phải lớn hơn 0.")

    ids = (
        list(point_ids)
        if point_ids is not None
        else [str(i) for i in range(len(pixels))]
    )
    if len(ids) != len(pixels):
        raise ValueError("Số point ID phải bằng số cặp calibration point.")
    if len(set(ids)) != len(ids):
        raise ValueError("Point ID không được trùng nhau.")

    _ensure_unique_points(pixels, name="Pixel points")
    _ensure_unique_points(worlds, name="World points")
    _ensure_two_dimensional_spread(pixels, name="Pixel points")
    _ensure_two_dimensional_spread(worlds, name="World points")

    matrix, mask = cv2.findHomography(
        pixels,
        worlds,
        method=cv2.RANSAC,
        ransacReprojThreshold=float(ransac_threshold_m),
    )
    if matrix is None or mask is None or not np.isfinite(matrix).all():
        raise ValueError("Không thể tính ma trận H từ các điểm đã cung cấp.")

    scale = float(matrix[2, 2])
    if abs(scale) > np.finfo(np.float64).eps:
        matrix = matrix / scale

    predicted_worlds = cv2.perspectiveTransform(
        pixels.reshape(-1, 1, 2),
        matrix,
    ).reshape(-1, 2)
    if not np.isfinite(predicted_worlds).all():
        raise ValueError("Ma trận H tạo ra tọa độ dự đoán không hợp lệ.")

    errors = np.linalg.norm(predicted_worlds - worlds, axis=1)
    inlier_mask = mask.reshape(-1).astype(bool)
    valid_count = int(np.count_nonzero(inlier_mask))
    if valid_count < MIN_POINT_COUNT:
        raise ValueError("Không đủ 4 điểm hợp lệ sau khi loại outlier.")

    rmse_inlier = _rmse(errors[inlier_mask])
    rmse_all = _rmse(errors)
    validation_errors = (
        _leave_one_out_errors(
            pixels,
            worlds,
            ransac_threshold_m=ransac_threshold_m,
        )
        if len(pixels) > MIN_POINT_COUNT
        else None
    )
    validation_rmse = None
    if validation_errors is not None:
        valid_validation_errors = validation_errors[inlier_mask]
        if np.isfinite(valid_validation_errors).all():
            validation_rmse = _rmse(valid_validation_errors)

    valid_ratio = valid_count / len(pixels)
    rating = _quality_rating(
        point_count=len(pixels),
        valid_ratio=valid_ratio,
        validation_rmse_m=validation_rmse,
    )

    return {
        "direction": "pixel_to_world",
        "method": "ransac",
        "ransac_threshold_m": float(ransac_threshold_m),
        "homography": matrix.astype(float).tolist(),
        "quality": {
            "valid_points": valid_count,
            "total_points": len(pixels),
            "valid_ratio": float(valid_ratio),
            "rmse_inlier_m": rmse_inlier,
            "rmse_all_m": rmse_all,
            "validation_rmse_m": validation_rmse,
            "rating": rating,
        },
        "points": [
            {
                "id": point_id,
                "valid": bool(is_valid),
                "predicted_world": {
                    "x": float(predicted[0]),
                    "y": float(predicted[1]),
                },
                "error_m": float(error),
                "validation_error_m": (
                    float(validation_errors[index])
                    if validation_errors is not None
                    and np.isfinite(validation_errors[index])
                    else None
                ),
            }
            for index, (point_id, is_valid, predicted, error) in enumerate(
                zip(
                    ids,
                    inlier_mask,
                    predicted_worlds,
                    errors,
                )
            )
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
def _as_point_array(
    points: Sequence[Sequence[float]],
    *,
    name: str,
) -> np.ndarray:
    """Chuyển danh sách tọa độ thành mảng ``N x 2`` hữu hạn."""
    try:
        array = np.asarray(points, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} phải chứa các cặp số hợp lệ.") from error

    if array.ndim != 2 or array.shape[1] != 2:
        raise ValueError(f"{name} phải có định dạng N x 2.")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} không được chứa NaN hoặc vô cực.")
    return array


# ─────────────────────────────────────────────────────────────────────────────
def _ensure_unique_points(points: np.ndarray, *, name: str) -> None:
    """Bảo đảm tập điểm không chứa hai tọa độ trùng nhau."""
    rounded = np.round(points, decimals=9)
    if len(np.unique(rounded, axis=0)) != len(points):
        raise ValueError(f"{name} không được chứa tọa độ trùng nhau.")


# ─────────────────────────────────────────────────────────────────────────────
def _ensure_two_dimensional_spread(points: np.ndarray, *, name: str) -> None:
    """Bảo đảm tập điểm phủ diện tích hai chiều và không gần thẳng hàng."""
    centered = points - np.mean(points, axis=0)
    singular_values = np.linalg.svd(centered, compute_uv=False)
    has_area = (
        len(singular_values) >= 2
        and singular_values[0] > np.finfo(np.float64).eps
        and singular_values[1] / singular_values[0] >= 1e-4
    )
    if not has_area:
        raise ValueError(f"{name} không được nằm trên cùng một đường thẳng.")


# ─────────────────────────────────────────────────────────────────────────────
def _rmse(errors: np.ndarray) -> float:
    """Tính căn bậc hai của trung bình bình phương sai số."""
    return float(np.sqrt(np.mean(np.square(errors))))


# ─────────────────────────────────────────────────────────────────────────────
def _leave_one_out_errors(
    pixels: np.ndarray,
    worlds: np.ndarray,
    *,
    ransac_threshold_m: float,
) -> np.ndarray:
    """Tính sai số từng điểm bằng H không sử dụng chính điểm đó."""
    validation_errors = np.full(len(pixels), np.nan, dtype=np.float64)

    for index in range(len(pixels)):
        training_pixels = np.delete(pixels, index, axis=0)
        training_worlds = np.delete(worlds, index, axis=0)
        matrix, _ = cv2.findHomography(
            training_pixels,
            training_worlds,
            method=cv2.RANSAC,
            ransacReprojThreshold=float(ransac_threshold_m),
        )
        if matrix is None or not np.isfinite(matrix).all():
            continue

        predicted = cv2.perspectiveTransform(
            pixels[index].reshape(1, 1, 2),
            matrix,
        ).reshape(2)
        if not np.isfinite(predicted).all():
            continue

        validation_errors[index] = np.linalg.norm(predicted - worlds[index])

    return validation_errors


# ─────────────────────────────────────────────────────────────────────────────
def _quality_rating(
    *,
    point_count: int,
    valid_ratio: float,
    validation_rmse_m: float | None,
) -> str:
    """Phân loại chất lượng từ tỷ lệ hợp lệ và sai số kiểm tra."""
    if point_count == MIN_POINT_COUNT:
        return "LIMITED"
    if validation_rmse_m is None:
        return "RECALIBRATE"
    if valid_ratio >= 0.9 and validation_rmse_m <= 0.10:
        return "GOOD"
    if valid_ratio >= 0.75 and validation_rmse_m <= 0.20:
        return "CHECK"
    return "RECALIBRATE"
