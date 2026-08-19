import cv2
import numpy as np
import pytest

from src.calibration import calculate_homography, project_pixel_to_world


# ─────────────────────────────────────────────────────────────────────────────
def _project(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Chiếu một tập điểm qua ma trận Homography cho dữ liệu kiểm thử."""
    return cv2.perspectiveTransform(
        points.astype(np.float64).reshape(-1, 1, 2),
        matrix,
    ).reshape(-1, 2)


# ─────────────────────────────────────────────────────────────────────────────
def test_project_pixel_to_world_applies_homogeneous_division() -> None:
    """Kiểm tra helper chiếu pixel thực hiện đúng phép chia tọa độ đồng nhất."""
    projected = project_pixel_to_world(
        (10, 20),
        [
            [2.0, 0.0, 4.0],
            [0.0, 3.0, 6.0],
            [0.0, 0.0, 2.0],
        ],
    )

    assert projected == pytest.approx((12.0, 33.0))


# ─────────────────────────────────────────────────────────────────────────────
def test_calculate_homography_recovers_mapping_and_rejects_outlier() -> None:
    """Kiểm tra service khôi phục đúng H và loại được một outlier."""
    pixels = np.array(
        [
            [120, 100],
            [960, 100],
            [1800, 100],
            [120, 540],
            [960, 540],
            [1800, 540],
            [120, 980],
            [960, 980],
            [1800, 980],
        ],
        dtype=np.float64,
    )
    expected_matrix = np.array(
        [
            [0.008, 0.001, -2.0],
            [-0.0005, 0.010, 1.5],
            [0.00001, -0.00002, 1.0],
        ],
        dtype=np.float64,
    )
    worlds = _project(pixels, expected_matrix)
    worlds[-1] += np.array([1.5, -1.0])

    result = calculate_homography(
        pixels,
        worlds,
        point_ids=[f"point-{index}" for index in range(len(pixels))],
    )

    assert result["quality"]["valid_points"] == 8
    assert result["quality"]["total_points"] == 9
    assert result["quality"]["rmse_inlier_m"] < 1e-6
    assert result["quality"]["validation_rmse_m"] < 1e-5
    assert result["quality"]["rating"] == "CHECK"
    assert result["points"][-1]["valid"] is False
    assert result["points"][-1]["validation_error_m"] > 1.0

    actual_matrix = np.asarray(result["homography"])
    np.testing.assert_allclose(actual_matrix, expected_matrix, rtol=1e-5, atol=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
def test_exactly_four_points_have_limited_quality_rating() -> None:
    """Kiểm tra bốn điểm chỉ đủ tính H nhưng chưa đủ đánh giá chất lượng."""
    pixels = [[0, 0], [100, 0], [100, 100], [0, 100]]
    worlds = [[0, 0], [1, 0], [1, 1], [0, 1]]

    result = calculate_homography(pixels, worlds)

    assert result["quality"]["valid_points"] == 4
    assert result["quality"]["rating"] == "LIMITED"
    assert result["quality"]["validation_rmse_m"] is None
    assert all(point["validation_error_m"] is None for point in result["points"])


# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("pixels", "worlds", "message"),
    [
        (
            [[0, 0], [0, 0], [100, 100], [0, 100]],
            [[0, 0], [1, 0], [1, 1], [0, 1]],
            "tọa độ trùng nhau",
        ),
        (
            [[0, 0], [100, 0], [200, 0], [300, 0]],
            [[0, 0], [1, 0], [2, 0], [3, 0]],
            "cùng một đường thẳng",
        ),
    ],
)
def test_invalid_point_geometry_is_rejected(pixels, worlds, message) -> None:
    """Kiểm tra service từ chối tập điểm trùng hoặc thẳng hàng."""
    with pytest.raises(ValueError, match=message):
        calculate_homography(pixels, worlds)
