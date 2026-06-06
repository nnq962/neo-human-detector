from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from src.reid_utils import normalize_embedding


@dataclass
class TrackerConfig:
    """Các ngưỡng dùng chung cho cả tầng track tạm và gallery bền vững."""

    # TrackManager: quản lý vòng đời track_id tạm từ ByteTrack.
    buffer_min     : int = 200   # cần tối thiểu N embedding tốt trước khi gán global_id
    grace_period   : int = 20   # giữ track mất dấu tạm thời thêm N frame
    update_interval: int = 120  # chu kỳ update EMA embedding, tính theo frame
    max_buffer_size: int = 250   # giới hạn buffer embedding của mỗi track

    # Bbox quality: quyết định frame nào đủ sạch để extract ReID embedding.
    min_detection_conf       : float = 0.50  # bỏ detection confidence thấp
    min_bbox_width           : float = 30.0  # bỏ người quá nhỏ/xa camera
    min_bbox_height          : float = 70.0
    min_bbox_aspect_ratio    : float = 0.18  # width / height, giữ được người ngồi
    max_bbox_aspect_ratio    : float = 1.50
    edge_margin_ratio        : float = 0.02  # bỏ bbox sát mép frame
    overlap_iou_threshold    : float = 0.25  # bbox đè nhau rõ thì bỏ
    overlap_ioa_threshold    : float = 0.45  # intersection / bbox nhỏ hơn
    stable_bbox_window       : int   = 100    # cần ổn định trong N frame gần nhất
    stable_center_shift_ratio: float = 0.20  # tâm bbox dao động tối đa / đường chéo bbox
    stable_size_change_ratio : float = 0.25  # kích thước bbox dao động tối đa
    laplacian_var_threshold  : float = 50.0  # crop mờ quá thì bỏ

    # Gallery: quản lý global_id bền vững xuyên suốt session.
    sim_threshold_match : float = 0.85  # cosine >= ngưỡng này thì coi là cùng người
    sim_threshold_unsure: float = 0.65  # dưới match nhưng đủ gần thì chờ thêm
    ema_alpha           : float = 0.75  # EMA cao hơn nghĩa là embedding cũ ổn định hơn
    max_samples         : int   = 5     # số sample gần nhất giữ kèm mỗi global_id
    gallery_ttl_minutes : float = 2.0   # quá N phút không gặp lại thì xóa global_id

    @property
    def gallery_ttl_seconds(self) -> float:
        """Số giây tương ứng với gallery_ttl_minutes."""
        return self.gallery_ttl_minutes * 60


class TrackStatus(Enum):
    """Trạng thái vòng đời của một ByteTrack track_id."""

    NEW       = "new"        # vừa xuất hiện, đang gom embedding
    PENDING   = "pending"    # đang query gallery, hiện vẫn chạy đồng bộ
    CONFIRMED = "confirmed"  # đã có global_id bền vững
    UNCERTAIN = "uncertain"  # nhập nhằng, có thể chờ thêm embedding


@dataclass
class TrackState:
    """Trạng thái ngắn hạn của một người đang được ByteTrack theo dõi."""

    track_id        : int
    status          : TrackStatus = TrackStatus.NEW
    embedding_buffer: list[np.ndarray] = field(default_factory=list)
    bbox_history    : list[tuple] = field(default_factory=list)
    global_id       : int | None = None
    frame_count     : int = 0
    good_frame_count: int = 0
    last_seen       : int = 0
    confidence      : float = 0.0
    bbox            : tuple | None = None
    confirmed_at    : int = 0

    def add_embedding(
        self, embedding: np.ndarray, frame_idx: int, max_buffer: int = 20
    ) -> None:
        """Lưu embedding đã chuẩn hóa và cắt buffer nếu quá dài."""
        self.embedding_buffer.append(normalize_embedding(embedding))
        self.good_frame_count += 1
        self.last_seen = frame_idx
        if len(self.embedding_buffer) > max_buffer:
            self.embedding_buffer.pop(0)

    def add_bbox(self, bbox: tuple, max_history: int) -> None:
        """Lưu lịch sử bbox để kiểm tra track có ổn định hay không."""
        self.bbox_history.append(tuple(float(v) for v in bbox))
        if len(self.bbox_history) > max_history:
            self.bbox_history.pop(0)

    def mean_embedding(self) -> np.ndarray:
        """Lấy embedding đại diện của track rồi chuẩn hóa lại về norm 1."""
        return normalize_embedding(np.mean(self.embedding_buffer, axis=0))

    def is_confirmed(self) -> bool:
        return self.status == TrackStatus.CONFIRMED

    def frames_since_confirmed(self, frame_idx: int) -> int:
        return frame_idx - self.confirmed_at


@dataclass
class GalleryEntry:
    """Một danh tính bền vững trong gallery."""

    global_id   : int
    embedding   : np.ndarray                                      # embedding đại diện, được update bằng EMA
    samples     : list[np.ndarray] = field(default_factory=list)  # vài mẫu gần nhất
    last_seen   : int = 0                                         # frame_idx lần cuối global_id này được match/update
    last_seen_at: float = field(default_factory=time.monotonic)   # thời điểm thật lần cuối gặp
    hit_count   : int = 0                                         # số lần global_id được match thành công
