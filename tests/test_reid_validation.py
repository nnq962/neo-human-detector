"""Kiểm thử ràng buộc số của cấu hình ReID dùng chung với frontend."""

import pytest
from pydantic import ValidationError

from api.models.reid import ReIdConfigUpdate


# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "payload",
    [
        {"embedding": {"batch_size": 1.5}},
        {"track": {"buffer_min": 0}},
        {"track": {"grace_period": -1}},
        {"quality": {"overlap_iou_threshold": 1.01}},
        {"quality": {"stable_center_shift_ratio": -0.01}},
        {"gallery": {"max_samples": 0}},
        {"gallery": {"ttl_minutes": -0.1}},
    ],
)
def test_reid_rejects_values_outside_frontend_contract(payload: dict) -> None:
    """Kiểm tra backend từ chối các giá trị mà frontend không cho phép nhập."""
    with pytest.raises(ValidationError):
        ReIdConfigUpdate.model_validate(payload)


# ─────────────────────────────────────────────────────────────────────────────
def test_reid_accepts_zero_ttl_and_unbounded_stability_ratios() -> None:
    """Kiểm tra frontend có thể gửi đủ miền hợp lệ được backend hỗ trợ."""
    config = ReIdConfigUpdate.model_validate(
        {
            "quality": {
                "stable_center_shift_ratio": 1.25,
                "stable_size_change_ratio": 2.0,
            },
            "gallery": {"ttl_minutes": 0},
        }
    )

    assert config.quality is not None
    assert config.quality.stable_center_shift_ratio == 1.25
    assert config.quality.stable_size_change_ratio == 2.0
    assert config.gallery is not None
    assert config.gallery.ttl_minutes == 0
