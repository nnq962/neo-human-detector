import json
import os
import time
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import HTTPException
from utils import LOGGER


MEDIAMTX_API_URL = os.getenv("MEDIAMTX_API_URL", "http://127.0.0.1:9997/v3").rstrip("/")
MEDIAMTX_WEBRTC_BASE_URL = os.getenv("MEDIAMTX_WEBRTC_BASE_URL", "").rstrip("/")


def build_mediamtx_url(path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"

    return f"{MEDIAMTX_API_URL}{normalized_path}"


def request_mediamtx(path: str, method: str = "GET", payload: Optional[dict] = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        build_mediamtx_url(path),
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=5) as response:
            response_text = response.read().decode("utf-8")
    except HTTPError as e:
        error_text = e.read().decode("utf-8", errors="replace")
        raise HTTPException(
            status_code=502,
            detail=f"MediaMTX request failed with HTTP {e.code}: {error_text}",
        ) from e
    except URLError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to connect to MediaMTX API: {e.reason}",
        ) from e

    return json.loads(response_text) if response_text else {}


def wait_for_path_ready(path_name: str) -> bool:
    for attempt in range(5):
        if attempt > 0:
            time.sleep(0.8)

        status = request_mediamtx(f"/paths/get/{path_name}")

        if status.get("ready") is True:
            return True

    return False


def build_path_payload(camera: dict) -> dict:
    stream = camera["stream"]
    return {
        "source": stream["source"],
        "sourceProtocol": stream.get("protocol", "tcp"),
        "sourceOnDemand": stream.get("on_demand", True),
    }


def delete_camera_path(camera_id: str, ignore_missing: bool = True) -> None:
    try:
        request_mediamtx(f"/config/paths/delete/{camera_id}", method="DELETE")
        LOGGER.info("Deleted MediaMTX camera path: %s", camera_id)
    except HTTPException as e:
        if not ignore_missing or e.status_code != 502 or "HTTP 404" not in str(e.detail):
            raise


def upsert_camera_path(camera: dict) -> None:
    camera_id = camera["id"]

    if not camera.get("enabled", True):
        LOGGER.info("Camera disabled; removing MediaMTX path: %s", camera_id)
        delete_camera_path(camera_id, ignore_missing=True)
        return

    delete_camera_path(camera_id, ignore_missing=True)
    payload = build_path_payload(camera)
    request_mediamtx(
        f"/config/paths/add/{camera_id}",
        method="POST",
        payload=payload,
    )
    LOGGER.info("Upserted MediaMTX camera path: %s | %s", camera_id, payload["source"])


def get_webrtc_base_url(hostname: Optional[str] = None, scheme: str = "http") -> str:
    if MEDIAMTX_WEBRTC_BASE_URL:
        return MEDIAMTX_WEBRTC_BASE_URL

    if hostname:
        return f"{scheme}://{hostname}:8889"

    return "http://127.0.0.1:8889"


def build_webrtc_address(path_name: str, base_url: Optional[str] = None) -> str:
    return f"{(base_url or get_webrtc_base_url()).rstrip('/')}/{quote(path_name, safe='')}"


def attach_webrtc_address(camera: dict, base_url: Optional[str] = None) -> dict:
    camera_data = dict(camera)
    camera_id = camera_data.get("id")

    if camera_id:
        camera_data["webrtc_address"] = build_webrtc_address(camera_id, base_url)

    return camera_data
