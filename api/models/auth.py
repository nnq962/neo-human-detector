"""Model request và response cho xác thực web."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Payload đăng nhập bằng mật khẩu cấu hình."""

    password: str = Field(min_length=1, max_length=1024)


class SessionStatus(BaseModel):
    """Trạng thái phiên đăng nhập hiện tại."""

    authenticated: bool
    enabled: bool
    configured: bool
