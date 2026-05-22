import os
import time
from pathlib import Path

import yaml
import requests

MEDIAMTX_API = "http://127.0.0.1:9997"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "default.yaml"
FALLBACK_CONFIG_PATH = Path("/app/config.yaml")


def get_config_path() -> Path:
    config_path = Path(os.getenv("CAMERA_CONFIG_PATH", DEFAULT_CONFIG_PATH))

    if config_path.exists():
        return config_path

    return FALLBACK_CONFIG_PATH


def load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def wait_for_mediamtx(max_attempts: int = 30) -> None:
    for _ in range(max_attempts):
        try:
            requests.get(f"{MEDIAMTX_API}/v3/config/get", timeout=1)
            return
        except requests.RequestException:
            time.sleep(1)

    raise RuntimeError("MediaMTX API is not ready.")


def build_path_payload(camera: dict) -> dict:
    return {
        "source": camera["source"],
        "sourceProtocol": camera.get("source_protocol", camera.get("sourceProtocol", "tcp")),
        "sourceOnDemand": camera.get("source_on_demand", camera.get("sourceOnDemand", True)),
    }


def load_cameras(config: dict) -> None:
    for camera in config.get("cameras", []):
        if not camera.get("enabled", True):
            continue

        camera_id = camera["id"]
        url = f"{MEDIAMTX_API}/v3/config/paths/add/{camera_id}"
        response = requests.post(url, json=build_path_payload(camera), timeout=5)

        print(camera_id, response.status_code, response.text)


def main() -> None:
    config_path = get_config_path()
    config = load_config(config_path)

    wait_for_mediamtx()
    load_cameras(config)


if __name__ == "__main__":
    main()
