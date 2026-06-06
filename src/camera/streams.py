"""
Helper tạo source list cho Ultralytics/RTSP streams.

YOLO batch stream có thể nhận một file text, mỗi dòng là một source.
File này gom logic đó ra khỏi config loader để việc đọc config không còn
nhất thiết phải có side effect ghi file.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, List, Mapping, Sequence

if TYPE_CHECKING:
    from src.camera.models import Camera


# -----------------------------------------------------------------------------
def build_rtsp_stream_sources(cameras: Sequence[Camera]) -> List[str]:
    """Lấy danh sách source từ các camera đang bật và đủ điều kiện detect."""
    return [
        camera.source.strip()
        for camera in cameras
        if camera.is_ready_for_detection() and camera.source.strip()
    ]


# -----------------------------------------------------------------------------
def build_rtsp_stream_sources_from_config(config: Mapping[str, Any]) -> List[str]:
    """Lấy danh sách source trực tiếp từ config dict, chưa cần parse Camera object."""
    cameras_data = config.get("cameras") or []
    if not isinstance(cameras_data, list):
        return []

    sources: List[str] = []
    for camera_data in cameras_data:
        if not isinstance(camera_data, Mapping):
            continue
        if not camera_data.get("enabled", True):
            continue

        source = str(camera_data.get("source") or "").strip()
        if source:
            sources.append(source)

    return sources


# -----------------------------------------------------------------------------
def write_rtsp_streams_file(
    sources: Iterable[str],
    output_path: str | Path,
) -> Path:
    """
    Ghi file streams theo format mỗi dòng một source.

    Hàm trả về path đã ghi để runtime có thể đưa vào `YoloDetectorConfig.source`.
    """
    streams_path = Path(output_path)
    normalized_sources = [source.strip() for source in sources if source.strip()]
    content = "\n".join(normalized_sources)

    if content:
        content += "\n"

    streams_path.parent.mkdir(parents=True, exist_ok=True)
    streams_path.write_text(content, encoding="utf-8")

    return streams_path
