"""
Kiểu dữ liệu chuẩn cho pipeline ReID.

Các dataclass ở đây là contract giữa runtime, track manager và identity gallery.
Điểm quan trọng với multi-camera: ByteTrack id chỉ là id tạm, còn key nội bộ của
ReID luôn gồm cả `camera_id` để tránh trùng track giữa các camera.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

from src.reid.utils import normalize_embedding


BBoxXYXY = tuple[float, float, float, float]


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ReIdConfig:
    """Các ngưỡng dùng chung cho track tạm, crop quality và identity gallery."""

    enabled               : bool          = False   # Bật/tắt toàn bộ ReID stage.
    zone_only             : bool          = True    # Chỉ ReID bbox nằm trong zone nếu True.
    require_occupied_zone : bool          = True    # Chỉ ReID bbox thuộc zone đã OCCUPIED.
    model_path            : Optional[str] = None    # Đường dẫn weights ReID, None dùng default.
    device                : str           = "auto"  # Device chạy model: auto/cpu/cuda/mps.
    embedding_batch_size  : int           = 32      # Batch size khi extract embedding từ crop.

    # Track manager: quản lý vòng đời track_id tạm từ ByteTrack.
    buffer_min              : int = 200   # Cần tối thiểu N embedding tốt trước khi confirm global_id.
    grace_period            : int = 20    # Giữ track mất dấu tạm thời thêm N frame trước khi xóa.
    update_interval         : int = 120   # Chu kỳ refresh embedding đại diện sau khi đã confirm.
    max_buffer_size         : int = 250   # Số embedding tối đa giữ trong buffer của mỗi track.
    gallery_cleanup_interval: int = 1800  # Chu kỳ frame để dọn global_id quá lâu không gặp.
    max_reverify_misses     : int = 3     # Số lần reverify fail liên tiếp trước khi detach.

    # Bbox quality: quyết định frame nào đủ sạch để extract ReID embedding.
    overlap_iou_threshold     : float = 0.25  # Bỏ crop nếu IoU với người khác quá cao.
    overlap_ioa_threshold     : float = 0.45  # Bỏ crop nếu phần lớn bbox nhỏ bị người khác che.
    stable_bbox_window        : int   = 100   # Số frame gần nhất dùng để kiểm tra bbox ổn định.
    stable_center_shift_ratio : float  = 0.20 # Tâm bbox dao động tối đa so với đường chéo bbox.
    stable_size_change_ratio  : float = 0.25  # Diện tích bbox dao động tối đa quanh mean area.
    laplacian_var_threshold   : float = 50.0  # Bỏ crop bị mờ, đo bằng Laplacian variance.

    # Gallery: quản lý global_id bền vững xuyên suốt runtime.
    sim_threshold_match : float = 0.85  # Cosine >= ngưỡng này thì coi là cùng người.
    ema_alpha           : float = 0.75  # EMA càng cao càng giữ embedding cũ ổn định hơn.
    max_samples         : int   = 5     # Số embedding sample gần nhất giữ kèm mỗi global_id.
    gallery_ttl_minutes : float = 2.0   # Xóa global_id nếu quá N phút không gặp lại.

    @property
    def gallery_ttl_seconds(self) -> float:
        """Số giây tương ứng với gallery_ttl_minutes."""
        return self.gallery_ttl_minutes * 60


# ─────────────────────────────────────────────────────────────────────────────
class ReIdTrackStatus(Enum):
    """Trạng thái ReID của một track trong gallery."""

    NEW     = "new"      # Chưa match profile cũ; đang tích embedding hoặc vừa tạo global_id mới.
    MATCHED = "matched"  # Đã dùng lại global_id từ profile có sẵn trong gallery.


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ReIdTrackKey:
    """
    Định danh track tạm trong ReID.

    ByteTrack id có thể không đủ an toàn khi nhiều camera chạy chung runtime, nên
    luôn gắn thêm camera_id.
    """

    camera_id: str
    track_id : int


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ReIdCandidate:
    """Một detection đủ điều kiện đưa vào ReID stage."""

    camera_id      : str
    track_id       : int
    detection_index: int
    bbox           : BBoxXYXY
    confidence     : float
    zone_name      : Optional[str] = None

    @property
    def key(self) -> ReIdTrackKey:
        """Track key nội bộ của candidate."""
        return ReIdTrackKey(self.camera_id, self.track_id)


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ReIdAssignment:
    """Kết quả ReID dùng để enrich lại InferenceFrame."""

    camera_id      : str
    track_id       : int
    detection_index: int
    global_id      : Optional[int]
    similarity     : Optional[float]
    status         : ReIdTrackStatus


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ReIdTrackState:
    """Trạng thái ngắn hạn của một track đang được ByteTrack theo dõi."""

    key             : ReIdTrackKey
    status          : ReIdTrackStatus = ReIdTrackStatus.NEW
    embedding_buffer: list[np.ndarray] = field(default_factory=list)
    bbox_history    : list[BBoxXYXY] = field(default_factory=list)
    global_id       : Optional[int] = None
    similarity      : Optional[float] = None
    frame_count     : int = 0
    good_frame_count: int = 0
    last_seen       : int = 0
    confidence      : float = 0.0
    bbox            : Optional[BBoxXYXY] = None
    matched_at      : int = 0
    reverify_miss_count: int = 0

    def add_embedding(
        self,
        embedding: np.ndarray,
        frame_idx: int,
        max_buffer: int,
    ) -> None:
        """Lưu embedding đã chuẩn hóa và cắt buffer nếu quá dài."""
        self.embedding_buffer.append(normalize_embedding(embedding))
        self.good_frame_count += 1
        self.last_seen = frame_idx
        if len(self.embedding_buffer) > max_buffer:
            self.embedding_buffer.pop(0)

    def add_bbox(self, bbox: BBoxXYXY, max_history: int) -> None:
        """Lưu lịch sử bbox để kiểm tra track có ổn định hay không."""
        self.bbox_history.append(tuple(float(value) for value in bbox))
        if len(self.bbox_history) > max_history:
            self.bbox_history.pop(0)

    def mean_embedding(self) -> np.ndarray:
        """Lấy embedding đại diện của track rồi chuẩn hóa lại về norm 1."""
        return normalize_embedding(np.mean(self.embedding_buffer, axis=0))

    def is_matched(self) -> bool:
        return self.status == ReIdTrackStatus.MATCHED

    def frames_since_matched(self, frame_idx: int) -> int:
        return frame_idx - self.matched_at


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class IdentityProfile:
    """Một danh tính bền vững trong gallery."""

    global_id   : int
    embedding   : np.ndarray
    samples     : list[np.ndarray] = field(default_factory=list)
    last_seen   : int = 0
    last_seen_at: float = field(default_factory=time.monotonic)
    hit_count   : int = 0


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class IdentityMatchResult:
    """Kết quả query gallery: matched với người cũ hoặc tạo identity mới."""

    status    : ReIdTrackStatus
    global_id : Optional[int]
    similarity: float
