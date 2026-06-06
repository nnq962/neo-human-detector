from pathlib import Path

import yaml

from src.camera import build_rtsp_stream_sources_from_config, write_rtsp_streams_file


def _build_rtsp_streams_file(cfg: dict, config_path: Path) -> None:
    streams_path = config_path.parent / "rtsp.streams"
    sources = build_rtsp_stream_sources_from_config(cfg)

    write_rtsp_streams_file(sources, streams_path)
    cfg.setdefault("source", {})["streams_file"] = str(streams_path)


def load_config(path: str = "configs/default.yaml") -> dict:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    _build_rtsp_streams_file(cfg, config_path)
    return cfg
