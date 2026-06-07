"""
Package ReID cho pipeline mới.

Public API cố ý không import embedder ở top-level để tránh kéo torch khi ReID tắt.
"""

from src.reid.candidate_selector import select_reid_candidates
from src.reid.gallery import IdentityGallery
from src.reid.pipeline import ReIdPipeline
from src.reid.track_manager import ReIdTrackManager
from src.reid.types import (
    IdentityMatchResult,
    IdentityProfile,
    ReIdAssignment,
    ReIdCandidate,
    ReIdConfig,
    ReIdTrackKey,
    ReIdTrackState,
    ReIdTrackStatus,
)

__all__ = [
    "IdentityGallery",
    "IdentityMatchResult",
    "IdentityProfile",
    "ReIdAssignment",
    "ReIdCandidate",
    "ReIdConfig",
    "ReIdPipeline",
    "ReIdTrackKey",
    "ReIdTrackManager",
    "ReIdTrackState",
    "ReIdTrackStatus",
    "select_reid_candidates",
]
