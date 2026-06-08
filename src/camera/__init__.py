"""
Module camera gom các thành phần liên quan tới camera input.

Package này export trực tiếp public API để IDE/type checker đọc được đúng kiểu
trả về, ví dụ `load_cameras_from_config` sẽ hiện rõ là `List[Camera]`.
"""

from src.camera.streams import (
    build_rtsp_stream_sources,
    build_rtsp_stream_sources_from_config,
    write_rtsp_streams_file,
)
from src.camera.models import Camera, CameraStreamConfig
from src.camera.loader import flatten_camera_zones, load_cameras_from_config


__all__ = [
    "Camera",
    "CameraStreamConfig",
    "build_rtsp_stream_sources",
    "build_rtsp_stream_sources_from_config",
    "flatten_camera_zones",
    "load_cameras_from_config",
    "write_rtsp_streams_file",
]
