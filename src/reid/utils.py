"""
Hàm tiện ích nhỏ cho embedding ReID.
"""

from __future__ import annotations

import numpy as np

BBoxXYXY = tuple[float, float, float, float]


# ─────────────────────────────────────────────────────────────────────────────
def normalize_embedding(embedding: np.ndarray) -> np.ndarray:
    """Đưa embedding về vector float32 một chiều có L2 norm = 1."""
    if hasattr(embedding, "detach"):
        embedding = embedding.detach().cpu().numpy()

    embedding = np.asarray(embedding, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(embedding))
    if norm <= 1e-12:
        raise ValueError("Cannot normalize a zero embedding")

    return embedding / norm


# ─────────────────────────────────────────────────────────────────────────────
def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity ổn định kể cả khi đầu vào chưa được normalize."""
    try:
        a = normalize_embedding(a)
        b = normalize_embedding(b)
    except ValueError:
        return 0.0

    return float(np.dot(a, b))


# ─────────────────────────────────────────────────────────────────────────────
def crop(frame: np.ndarray, bbox: BBoxXYXY) -> np.ndarray:
    x1, y1, x2, y2 = map(int, bbox)
    height, width = frame.shape[:2]
    return frame[max(0, y1):min(height, y2), max(0, x1):min(width, x2)]


# ─────────────────────────────────────────────────────────────────────────────
def fmt_sim(similarity: float | None) -> str:
    return "-" if similarity is None else f"{similarity:.3f}"
