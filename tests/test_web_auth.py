"""Kiểm thử xác thực web và ranh giới API công khai."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Request
from starlette.responses import Response

from api.models.auth import LoginRequest
from api.routes.auth import SESSION_COOKIE_NAME, login
from api.routes.public import _serialize_public_camera
from api.routes.websocket import _require_private_websocket
from api.server import require_authenticated_api
from api.services import config_store
from api.services.auth import (
    AuthService,
    AuthSettings,
    InvalidCredentialsError,
    LoginRateLimitedError,
    auth_service,
)


class FakeClock:
    """Đồng hồ monotonic điều khiển được trong kiểm thử."""

    def __init__(self) -> None:
        """Khởi tạo đồng hồ tại mốc không."""
        self.now = 0.0

    # ─────────────────────────────────────────────────────────────────────────
    def __call__(self) -> float:
        """Trả thời gian hiện tại."""
        return self.now

    # ─────────────────────────────────────────────────────────────────────────
    def advance(self, seconds: float) -> None:
        """Tiến đồng hồ thêm số giây chỉ định."""
        self.now += seconds


class FakeWebSocket:
    """WebSocket tối thiểu để kiểm tra handshake xác thực."""

    def __init__(self, *, token: str | None = None) -> None:
        """Khởi tạo header, cookie và bộ nhớ close code giả."""
        self.headers = {"host": "testserver", "origin": "http://testserver"}
        self.cookies = {SESSION_COOKIE_NAME: token} if token else {}
        self.url = SimpleNamespace(scheme="ws")
        self.accepted = False
        self.close_code: int | None = None

    # ─────────────────────────────────────────────────────────────────────────
    async def accept(self) -> None:
        """Ghi nhận server đã chấp nhận handshake."""
        self.accepted = True

    # ─────────────────────────────────────────────────────────────────────────
    async def close(self, *, code: int, reason: str) -> None:
        """Ghi nhận close code; reason chỉ mô phỏng chữ ký Starlette."""
        del reason
        self.close_code = code


# ─────────────────────────────────────────────────────────────────────────────
def _settings(password: str, *, ttl: int = 60) -> AuthSettings:
    """Tạo cấu hình auth gọn dùng cho unit test."""
    return AuthSettings(
        enabled=True,
        password=password,
        session_ttl_seconds=ttl,
        max_login_failures=2,
        login_window_seconds=30,
        login_block_seconds=90,
        secure_cookie=False,
        allowed_origins=(),
    )


# ─────────────────────────────────────────────────────────────────────────────
def _request(
    path: str,
    *,
    method: str = "GET",
    cookie: str | None = None,
) -> Request:
    """Tạo Starlette Request tối thiểu để kiểm thử middleware và route trực tiếp."""
    headers = [(b"host", b"testserver")]
    if cookie:
        headers.append((b"cookie", cookie.encode("latin-1")))
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
def test_session_expires_and_password_change_revokes_it(monkeypatch) -> None:
    """Kiểm tra session hết hạn và bị thu hồi khi mật khẩu đổi."""
    clock = FakeClock()
    service = AuthService(clock=clock)
    first_password = "mat-khau-1"
    current_settings = _settings(first_password, ttl=10)
    monkeypatch.setattr(
        "api.services.auth.load_auth_settings",
        lambda: current_settings,
    )

    token, ttl = service.create_session("mat-khau-1", "client-1")
    assert ttl == 10
    assert service.is_session_valid(token)

    current_settings = _settings("mat-khau-2", ttl=10)
    assert not service.is_session_valid(token)

    current_settings = _settings(first_password, ttl=10)
    token, _ = service.create_session("mat-khau-1", "client-1")
    clock.advance(11)
    assert not service.is_session_valid(token)


# ─────────────────────────────────────────────────────────────────────────────
def test_login_rate_limit_blocks_repeated_failures(monkeypatch) -> None:
    """Kiểm tra client bị khóa tạm thời sau nhiều lần nhập sai."""
    clock = FakeClock()
    service = AuthService(clock=clock)
    settings = _settings("mat-khau-dung")
    monkeypatch.setattr("api.services.auth.load_auth_settings", lambda: settings)

    with pytest.raises(InvalidCredentialsError):
        service.create_session("sai-1", "client-1")
    with pytest.raises(InvalidCredentialsError):
        service.create_session("sai-2", "client-1")
    with pytest.raises(LoginRateLimitedError):
        service.create_session("mat-khau-dung", "client-1")

    clock.advance(91)
    token, _ = service.create_session("mat-khau-dung", "client-1")
    assert service.is_session_valid(token)


# ─────────────────────────────────────────────────────────────────────────────
def test_private_websocket_rejects_invalid_session_with_auth_code(monkeypatch) -> None:
    """Kiểm tra WebSocket riêng tư trả code 4401 cho session sai."""
    websocket = FakeWebSocket(token="khong-hop-le")
    settings = _settings("mat-khau-test")
    monkeypatch.setattr("api.routes.websocket.load_auth_settings", lambda: settings)
    monkeypatch.setattr("api.routes.websocket.is_origin_allowed", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        "api.routes.websocket.auth_service.is_session_valid",
        lambda token: False,
    )

    allowed = asyncio.run(_require_private_websocket(websocket))

    assert not allowed
    assert websocket.accepted
    assert websocket.close_code == 4401


# ─────────────────────────────────────────────────────────────────────────────
def test_private_websocket_allows_valid_session(monkeypatch) -> None:
    """Kiểm tra WebSocket riêng tư đi tiếp khi Origin và session hợp lệ."""
    websocket = FakeWebSocket(token="hop-le")
    settings = _settings("mat-khau-test")
    monkeypatch.setattr("api.routes.websocket.load_auth_settings", lambda: settings)
    monkeypatch.setattr("api.routes.websocket.is_origin_allowed", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        "api.routes.websocket.auth_service.is_session_valid",
        lambda token: token == "hop-le",
    )

    allowed = asyncio.run(_require_private_websocket(websocket))

    assert allowed
    assert not websocket.accepted
    assert websocket.close_code is None


# ─────────────────────────────────────────────────────────────────────────────
def test_http_auth_and_public_camera_boundary(tmp_path: Path, monkeypatch) -> None:
    """Kiểm tra API riêng cần cookie và API public không lộ RTSP source."""
    config_path = tmp_path / "default.yaml"
    old_config_path = config_store.CONFIG_PATH
    config_store.CONFIG_PATH = str(config_path)
    config_store.save_config_data(
        {
            "web": {
                "auth": {
                    "enabled": True,
                    "password": "mat-khau-test",
                    "session_ttl_seconds": 60,
                }
            },
            "detection": {
                "model_id": "test-model",
                "conf": 0.5,
                "verbose": False,
            },
            "cameras": [
                {
                    "id": "cam-1",
                    "name": "Camera public",
                    "enabled": True,
                    "stream": {
                        "source": "rtsp://user:secret@example.test/stream",
                        "protocol": "tcp",
                        "on_demand": True,
                    },
                    "zones": [],
                }
            ],
        }
    )
    monkeypatch.setattr("api.services.mediamtx.MEDIAMTX_WEBRTC_BASE_URL", "")

    async def allowed_response(_: Request) -> Response:
        """Trả response đánh dấu middleware đã cho request đi tiếp."""
        return Response(status_code=204)

    try:
        auth_service.reset()
        protected_response = asyncio.run(
            require_authenticated_api(
                _request("/api/detection"),
                allowed_response,
            )
        )
        assert protected_response.status_code == 401

        public_response = asyncio.run(
            require_authenticated_api(
                _request("/api/public/cameras"),
                allowed_response,
            )
        )
        assert public_response.status_code == 204

        public_camera = _serialize_public_camera(
            config_store.get_config_data()["cameras"][0],
            _request("/api/public/cameras"),
        )
        assert "stream" not in public_camera
        assert "secret" not in str(public_camera)

        login_response = Response()
        session = login(
            LoginRequest(password="mat-khau-test"),
            _request("/api/auth/login", method="POST"),
            login_response,
        )
        assert session.authenticated
        set_cookie = login_response.headers["set-cookie"]
        assert "HttpOnly" in set_cookie
        cookie = set_cookie.split(";", 1)[0]
        assert cookie.startswith(f"{SESSION_COOKIE_NAME}=")

        authenticated_response = asyncio.run(
            require_authenticated_api(
                _request("/api/detection", cookie=cookie),
                allowed_response,
            )
        )
        assert authenticated_response.status_code == 204
    finally:
        auth_service.reset()
        config_store.CONFIG_PATH = old_config_path


# ─────────────────────────────────────────────────────────────────────────────
