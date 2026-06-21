"""
Package ReID.

Public API: ReIdPipeline, ReIdConfig, IdentityGallery.
torch không được import ở top-level để tránh kéo khi ReID tắt.
"""

from src.reid.datatypes import ReIdAssignment, ReIdCandidate, ReIdConfig
from src.reid.gallery import IdentityGallery
from src.reid.pipeline import ReIdPipeline

__all__ = [
    "IdentityGallery",
    "ReIdAssignment",
    "ReIdCandidate",
    "ReIdConfig",
    "ReIdPipeline",
]
