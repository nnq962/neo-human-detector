"""
Kiểu dữ liệu chuẩn cho camera.

Hiện tại zone vẫn nằm ở `src.models.Zone` để không làm vỡ code cũ.
Khi tách tiếp module `zones/`, field `zones` trong file này chỉ cần đổi import.
"""

from dataclasses import dataclass, field
from typing import List, Literal, Optional, Tuple

from src.models import Zone


CameraSourceProtocol = Literal["tcp", "udp", "multicast"]


# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class CameraStreamConfig:
    """
    Cấu hình stream của một camera.

    Các field này map gần trực tiếp sang MediaMTX path config và RTSP source list.
    """

    source: str
    source_protocol: CameraSourceProtocol = "tcp"
    source_on_demand: bool = True


# -----------------------------------------------------------------------------
@dataclass
class Camera:
    """
    Camera runtime dùng trong pipeline AI.

    `resolution` được điền sau khi detector đọc được frame đầu tiên.
    `zones` là danh sách zone thuộc riêng camera này.
    """

    id: str
    name: str
    stream: CameraStreamConfig
    zones: List[Zone] = field(default_factory=list)
    enabled: bool = True
    resolution: Optional[Tuple[int, int]] = None

    @property
    def source(self) -> str:
        """Trả RTSP/source URL để tương thích với code cũ."""
        return self.stream.source

    @property
    def source_protocol(self) -> CameraSourceProtocol:
        """Trả protocol đọc source, thường là tcp."""
        return self.stream.source_protocol

    @property
    def source_on_demand(self) -> bool:
        """Trả flag sourceOnDemand dùng cho MediaMTX."""
        return self.stream.source_on_demand

    @property
    def path_name(self) -> str:
        """Tên path trên MediaMTX, hiện dùng chính camera id."""
        return self.id

    @property
    def zone_count(self) -> int:
        """Số zone hợp lệ thuộc camera."""
        return len(self.zones)

    def is_ready_for_detection(self) -> bool:
        """Camera có đủ thông tin tối thiểu để đưa vào detector hay không."""
        return self.enabled and bool(self.id) and bool(self.source)
