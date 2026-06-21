from __future__ import annotations

import inspect
from collections.abc import Iterable
from typing import Any

import numpy as np

from utils import LOGGER

from src.media_sources.batch import StreamBatchReader, SyncBatchReader, _BaseBatch
from src.media_sources.detector import _classify_one, detect_source_type
from src.media_sources.models import SourceType
from src.media_sources.readers.base import BaseReader
from src.media_sources.readers.image import ImageReader
from src.media_sources.readers.rtsp import RtspReader
from src.media_sources.readers.video import VideoReader
from src.media_sources.readers.webcam import WebcamReader
from src.media_sources.readers.youtube import YoutubeReader

# ─────────────────────────────────────────────────────────────────────────────

_READER_MAP: dict[SourceType, type[BaseReader]] = {
    SourceType.IMAGE: ImageReader,
    SourceType.VIDEO: VideoReader,
    SourceType.WEBCAM: WebcamReader,
    SourceType.RTSP: RtspReader,
    SourceType.YOUTUBE: YoutubeReader,
}


def create_media_source(sources, **kwargs) -> BaseReader | _BaseBatch:
    """Tạo reader phù hợp theo loại nguồn (KHÔNG kết nối — lazy, mở khi open()/vào context).

    - Nguồn đơn (str/int/ndarray) → BaseReader con (dùng open/read/close độc lập).
    - List nguồn → batch đồng nhất (detect_source_type validate), gói trong:
        • StreamBatchReader nếu reader là stream (rtsp/webcam) — latest-frame realtime.
        • SyncBatchReader nếu tuần tự (image/video/youtube) — lockstep, không drop frame.

    kwargs dư thừa với constructor của reader sẽ bị lọc bỏ (log DEBUG) — xem _reader_kwargs.
    """
    if _is_sequence(sources):
        items = list(sources)
        if not items:
            raise ValueError("Danh sách sources không được rỗng.")
        source_type = detect_source_type(items)
        reader_cls = _READER_MAP[source_type]
        reader_kwargs = _reader_kwargs(reader_cls, kwargs)
        readers = [reader_cls(item, **reader_kwargs) for item in items]
        if reader_cls.is_stream:
            return StreamBatchReader(readers, frame_timeout=kwargs.get("frame_timeout", 2.0))
        return SyncBatchReader(readers)

    source_type = _classify_one(sources)
    reader_cls = _READER_MAP[source_type]
    return reader_cls(sources, **_reader_kwargs(reader_cls, kwargs))


# ─────────────────────────────────────────────────────────────────────────────


def _is_sequence(value: Any) -> bool:
    """True nếu là list nhiều nguồn — loại trừ str/bytes/ndarray (đều là nguồn đơn)."""
    return isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray, np.ndarray))


def _reader_kwargs(reader_cls: type[BaseReader], kwargs: dict[str, Any]) -> dict[str, Any]:
    """Chỉ giữ các kwargs mà constructor của reader chấp nhận; phần dư log DEBUG."""
    parameters = inspect.signature(reader_cls.__init__).parameters
    accepted = {
        name
        for name, parameter in parameters.items()
        if name not in {"self", "source"}
        and parameter.kind in {parameter.KEYWORD_ONLY, parameter.POSITIONAL_OR_KEYWORD}
    }
    selected = {name: value for name, value in kwargs.items() if name in accepted}
    ignored = sorted(set(kwargs) - set(selected))
    if ignored:
        LOGGER.debug("Bỏ qua kwargs không áp dụng cho %s: %s", reader_cls.__name__, ignored)
    return selected
