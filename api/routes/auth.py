"""Endpoint đăng nhập, kiểm tra phiên và đăng xuất."""

from fastapi import APIRouter, HTTPException, Request, Response, status

from api.models.auth import LoginRequest, SessionStatus
from api.services.auth import (
    AuthenticationConfigurationError,
    InvalidCredentialsError,
    LoginRateLimitedError,
    auth_service,
    load_auth_settings,
)


router = APIRouter()
SESSION_COOKIE_NAME = "neo_session"


# ─────────────────────────────────────────────────────────────────────────────
def _client_id(request: Request) -> str:
    """Lấy địa chỉ client ổn định để áp dụng giới hạn đăng nhập."""
    return request.client.host if request.client is not None else "unknown"


# ─────────────────────────────────────────────────────────────────────────────
def _use_secure_cookie(request: Request) -> bool:
    """Quyết định cờ Secure từ cấu hình hoặc scheme request hiện tại."""
    configured = load_auth_settings().secure_cookie
    return configured if configured is not None else request.url.scheme == "https"


# ─────────────────────────────────────────────────────────────────────────────
@router.get("/session", response_model=SessionStatus)
def get_session(request: Request) -> SessionStatus:
    """Trả trạng thái xác thực mà không làm lộ nội dung session."""
    settings = load_auth_settings()
    return SessionStatus(
        authenticated=(
            not settings.enabled
            or auth_service.is_session_valid(request.cookies.get(SESSION_COOKIE_NAME))
        ),
        enabled=settings.enabled,
        configured=bool(settings.password_hash),
    )


# ─────────────────────────────────────────────────────────────────────────────
@router.post("/login", response_model=SessionStatus)
def login(payload: LoginRequest, request: Request, response: Response) -> SessionStatus:
    """Xác thực password và đặt session cookie HttpOnly."""
    try:
        token, ttl_seconds = auth_service.create_session(
            payload.password,
            _client_id(request),
        )
    except LoginRateLimitedError as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Có quá nhiều lần đăng nhập thất bại. Vui lòng thử lại sau.",
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from error
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mật khẩu chưa chính xác. Vui lòng thử lại.",
        ) from error
    except AuthenticationConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=ttl_seconds,
        httponly=True,
        secure=_use_secure_cookie(request),
        samesite="strict",
        path="/",
    )
    return SessionStatus(authenticated=True, enabled=True, configured=True)


# ─────────────────────────────────────────────────────────────────────────────
@router.post("/logout", response_model=SessionStatus)
def logout(request: Request, response: Response) -> SessionStatus:
    """Thu hồi phiên phía máy chủ và xóa cookie trong trình duyệt."""
    auth_service.revoke_session(request.cookies.get(SESSION_COOKIE_NAME))
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=_use_secure_cookie(request),
        httponly=True,
        samesite="strict",
    )
    settings = load_auth_settings()
    return SessionStatus(
        authenticated=not settings.enabled,
        enabled=settings.enabled,
        configured=bool(settings.password_hash),
    )
