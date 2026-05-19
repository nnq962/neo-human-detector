from pathlib import Path

import yaml


def _build_rtsp_streams_file(cfg: dict, config_path: Path) -> None:
    cameras = cfg.get("cameras") or []
    sources = []

    for camera in cameras:
        source = camera.get("source") if isinstance(camera, dict) else None
        if source:
            sources.append(str(source).strip())

    if not sources:
        return

    streams_path = config_path.parent / "rtsp.streams"
    streams_path.write_text("\n".join(sources) + "\n", encoding="utf-8")
    cfg.setdefault("source", {})["streams_file"] = str(streams_path)

def load_config(path: str = "configs/default.yaml") -> dict:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    _build_rtsp_streams_file(cfg, config_path)
    return cfg
