"""Kiểm thử hợp đồng polygon zone giữa API và runtime loader."""

import pytest
from pydantic import ValidationError

from api.models.camera import Zone
from api.services.runtime import _validate_runtime_settings
from src.camera_initializer.camera_loader import _is_valid_polygon


@pytest.mark.parametrize(
    "points",
    [
        [[0, 0], [10, 10]],
        [[0, 0], [0, 0], [10, 10]],
        [[0, 0], [10, 10], [20, 20]],
    ],
)
def test_invalid_zone_is_rejected_by_api_and_runtime(points) -> None:
    """Kiểm tra zone thiếu điểm, trùng điểm hoặc thẳng hàng đều bị từ chối."""
    with pytest.raises(ValidationError):
        Zone(name="invalid", points=points)
    assert not _is_valid_polygon(points)


# ─────────────────────────────────────────────────────────────────────────────
def test_valid_concave_zone_is_accepted() -> None:
    """Kiểm tra polygon lõm hợp lệ vẫn được chấp nhận."""
    points = [[0, 0], [20, 0], [10, 10], [20, 20], [0, 20]]

    zone = Zone(name="concave", points=points)
    assert zone.points == points
    assert _is_valid_polygon(points)


# ─────────────────────────────────────────────────────────────────────────────
def test_runtime_start_rejects_invalid_zone_from_raw_yaml() -> None:
    """Kiểm tra YAML viết tay có zone lỗi làm runtime fail sớm thay vì bỏ qua."""
    settings = {"auto_start": False, "camera_ids": ["cam-1"]}
    config = {
        "cameras": [
            {
                "id": "cam-1",
                "enabled": True,
                "zones": [
                    {"name": "Zone lỗi", "points": [[0, 0], [10, 10]]},
                ],
            }
        ],
        "detection": {"model_id": "khong-can-resolve"},
    }

    with pytest.raises(ValueError, match="cam-1/Zone lỗi"):
        _validate_runtime_settings(settings, config)
