"""
Module camera gom các thành phần liên quan tới camera input.

Package này dùng lazy export để import nhẹ:
- Code chỉ cần ghi `rtsp.streams` sẽ không phải import numpy.
- Loader camera chỉ được import khi runtime thật sự cần parse camera/zone.
"""

from typing import Any


__all__ = [
    "Camera",
    "CameraStreamConfig",
    "build_rtsp_stream_sources",
    "build_rtsp_stream_sources_from_config",
    "flatten_camera_zones",
    "load_cameras_from_config",
    "write_rtsp_streams_file",
]


# -----------------------------------------------------------------------------
def __getattr__(name: str) -> Any:
    """Lazy import public API để tránh kéo dependency nặng khi chưa cần."""
    if name in {"Camera", "CameraStreamConfig"}:
        from src.camera.models import Camera, CameraStreamConfig

        return {
            "Camera": Camera,
            "CameraStreamConfig": CameraStreamConfig,
        }[name]

    if name in {"flatten_camera_zones", "load_cameras_from_config"}:
        from src.camera.loader import flatten_camera_zones, load_cameras_from_config

        return {
            "flatten_camera_zones": flatten_camera_zones,
            "load_cameras_from_config": load_cameras_from_config,
        }[name]

    if name in {
        "build_rtsp_stream_sources",
        "build_rtsp_stream_sources_from_config",
        "write_rtsp_streams_file",
    }:
        from src.camera.streams import (
            build_rtsp_stream_sources,
            build_rtsp_stream_sources_from_config,
            write_rtsp_streams_file,
        )

        return {
            "build_rtsp_stream_sources": build_rtsp_stream_sources,
            "build_rtsp_stream_sources_from_config": build_rtsp_stream_sources_from_config,
            "write_rtsp_streams_file": write_rtsp_streams_file,
        }[name]

    raise AttributeError(f"module 'src.camera' has no attribute '{name}'")
