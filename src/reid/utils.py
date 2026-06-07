"""
Hàm tiện ích nhỏ cho embedding ReID.
"""

from __future__ import annotations

import numpy as np


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
