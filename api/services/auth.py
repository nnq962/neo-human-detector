"""Xác thực mật khẩu và quản lý phiên web phía máy chủ."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable, Deque

from api.services import config_store


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_KEY_LENGTH = 32
SALT_LENGTH = 16
DEFAULT_SESSION_TTL_SECONDS = 8 * 60 * 60
DEFAULT_MAX_LOGIN_FAILURES = 5
DEFAULT_LOGIN_WINDOW_SECONDS = 60
DEFAULT_LOGIN_BLOCK_SECONDS = 5 * 60
SESSION_TOKEN_BYTES = 32


class AuthenticationConfigurationError(RuntimeError):
    """Báo cấu hình xác thực chưa đầy đủ hoặc không hợp lệ."""


class InvalidCredentialsError(ValueError):
    """Báo thông tin đăng nhập không chính xác."""


class LoginRateLimitedError(RuntimeError):
    """Báo client đã vượt quá số lần đăng nhập cho phép."""

    def __init__(self, retry_after_seconds: int) -> None:
        """Khởi tạo lỗi kèm số giây cần chờ trước khi thử lại."""
        super().__init__("Có quá nhiều lần đăng nhập thất bại.")
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class AuthSettings:
    """Cấu hình xác thực đã được chuẩn hóa từ YAML."""

    enabled: bool
    password_hash: str
    session_ttl_seconds: int
    max_login_failures: int
    login_window_seconds: int
    login_block_seconds: int
    secure_cookie: bool | None
    allowed_origins: tuple[str, ...]


@dataclass(frozen=True)
class SessionRecord:
    """Thông tin tối thiểu của một phiên đăng nhập trong bộ nhớ."""

    expires_at: float
    credential_fingerprint: str


# ─────────────────────────────────────────────────────────────────────────────
def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Băm mật khẩu bằng scrypt và trả chuỗi có đủ tham số kiểm tra."""
    if not password:
        raise ValueError("Mật khẩu không được để trống.")

    password_salt = salt or secrets.token_bytes(SALT_LENGTH)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=password_salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_KEY_LENGTH,
    )
    return (
        f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}"
        f"${password_salt.hex()}${digest.hex()}"
    )


# ─────────────────────────────────────────────────────────────────────────────
def verify_password(password: str, encoded_hash: str) -> bool:
    """Kiểm tra mật khẩu với chuỗi scrypt, trả ``False`` nếu hash hỏng."""
    try:
        algorithm, raw_n, raw_r, raw_p, raw_salt, raw_digest = encoded_hash.split("$")
        if algorithm != "scrypt":
            return False
        expected = bytes.fromhex(raw_digest)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(raw_salt),
            n=int(raw_n),
            r=int(raw_r),
            p=int(raw_p),
            dklen=len(expected),
        )
    except (TypeError, ValueError):
        return False

    return hmac.compare_digest(actual, expected)


# ─────────────────────────────────────────────────────────────────────────────
def _positive_int(value: object, default: int) -> int:
    """Chuẩn hóa một giá trị cấu hình thành số nguyên dương."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


# ─────────────────────────────────────────────────────────────────────────────
def load_auth_settings() -> AuthSettings:
    """Đọc và chuẩn hóa cấu hình xác thực web hiện tại."""
    config = config_store.get_config_data()
    web_config = config.get("web") or {}
    auth_config = web_config.get("auth") or {}
    raw_secure_cookie = auth_config.get("secure_cookie")
    secure_cookie = (
        raw_secure_cookie
        if isinstance(raw_secure_cookie, bool)
        else None
    )
    raw_origins = web_config.get("allowed_origins") or []
    allowed_origins = tuple(
        str(origin).rstrip("/")
        for origin in raw_origins
        if str(origin).strip()
    )

    return AuthSettings(
        enabled=auth_config.get("enabled", True) is True,
        password_hash=str(auth_config.get("password_hash") or "").strip(),
        session_ttl_seconds=_positive_int(
            auth_config.get("session_ttl_seconds"),
            DEFAULT_SESSION_TTL_SECONDS,
        ),
        max_login_failures=_positive_int(
            auth_config.get("max_login_failures"),
            DEFAULT_MAX_LOGIN_FAILURES,
        ),
        login_window_seconds=_positive_int(
            auth_config.get("login_window_seconds"),
            DEFAULT_LOGIN_WINDOW_SECONDS,
        ),
        login_block_seconds=_positive_int(
            auth_config.get("login_block_seconds"),
            DEFAULT_LOGIN_BLOCK_SECONDS,
        ),
        secure_cookie=secure_cookie,
        allowed_origins=allowed_origins,
    )


# ─────────────────────────────────────────────────────────────────────────────
def is_origin_allowed(origin: str | None, *, scheme: str, host: str) -> bool:
    """Kiểm tra Origin với chính host hiện tại và danh sách cấu hình."""
    if not origin:
        return True

    normalized_origin = origin.rstrip("/")
    same_origin = f"{scheme}://{host}".rstrip("/")
    settings = load_auth_settings()
    return normalized_origin == same_origin or normalized_origin in settings.allowed_origins


# ─────────────────────────────────────────────────────────────────────────────
def _credential_fingerprint(password_hash: str) -> str:
    """Tạo dấu vân tay để vô hiệu phiên cũ khi password hash thay đổi."""
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()


class AuthService:
    """Quản lý rate limit và session đăng nhập trong một process API."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        """Khởi tạo service với đồng hồ có thể thay thế trong kiểm thử."""
        self._clock = clock
        self._lock = threading.RLock()
        self._sessions: dict[str, SessionRecord] = {}
        self._failures: dict[str, Deque[float]] = defaultdict(deque)
        self._blocked_until: dict[str, float] = {}

    # ─────────────────────────────────────────────────────────────────────────
    def create_session(self, password: str, client_id: str) -> tuple[str, int]:
        """Xác thực password và tạo token phiên mới cho client."""
        settings = load_auth_settings()
        if not settings.enabled:
            raise AuthenticationConfigurationError("Xác thực web đang bị tắt.")
        if not settings.password_hash:
            raise AuthenticationConfigurationError(
                "Chưa cấu hình password_hash cho xác thực web."
            )

        now = self._clock()
        with self._lock:
            self._prune_locked(now)
            blocked_until = self._blocked_until.get(client_id, 0.0)
            if blocked_until > now:
                raise LoginRateLimitedError(max(1, int(blocked_until - now + 0.999)))

        if not verify_password(password, settings.password_hash):
            self._record_failure(client_id, settings, now)
            raise InvalidCredentialsError("Mật khẩu chưa chính xác.")

        token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
        token_digest = self._token_digest(token)
        record = SessionRecord(
            expires_at=now + settings.session_ttl_seconds,
            credential_fingerprint=_credential_fingerprint(settings.password_hash),
        )
        with self._lock:
            self._sessions[token_digest] = record
            self._failures.pop(client_id, None)
            self._blocked_until.pop(client_id, None)

        return token, settings.session_ttl_seconds

    # ─────────────────────────────────────────────────────────────────────────
    def is_session_valid(self, token: str | None) -> bool:
        """Kiểm tra token còn hạn và còn khớp password hash hiện hành."""
        if not token:
            return False

        settings = load_auth_settings()
        if not settings.enabled or not settings.password_hash:
            return False

        now = self._clock()
        token_digest = self._token_digest(token)
        with self._lock:
            self._prune_locked(now)
            record = self._sessions.get(token_digest)
            if record is None:
                return False
            if record.credential_fingerprint != _credential_fingerprint(
                settings.password_hash
            ):
                self._sessions.pop(token_digest, None)
                return False
            return True

    # ─────────────────────────────────────────────────────────────────────────
    def revoke_session(self, token: str | None) -> None:
        """Thu hồi token nếu token đang tồn tại."""
        if not token:
            return
        with self._lock:
            self._sessions.pop(self._token_digest(token), None)

    # ─────────────────────────────────────────────────────────────────────────
    def reset(self) -> None:
        """Xóa toàn bộ phiên và rate-limit, chủ yếu phục vụ kiểm thử."""
        with self._lock:
            self._sessions.clear()
            self._failures.clear()
            self._blocked_until.clear()

    # ─────────────────────────────────────────────────────────────────────────
    def _record_failure(
        self,
        client_id: str,
        settings: AuthSettings,
        now: float,
    ) -> None:
        """Ghi nhận lần đăng nhập sai và khóa client khi chạm ngưỡng."""
        with self._lock:
            failures = self._failures[client_id]
            cutoff = now - settings.login_window_seconds
            while failures and failures[0] <= cutoff:
                failures.popleft()
            failures.append(now)
            if len(failures) >= settings.max_login_failures:
                self._blocked_until[client_id] = now + settings.login_block_seconds
                failures.clear()

    # ─────────────────────────────────────────────────────────────────────────
    def _prune_locked(self, now: float) -> None:
        """Loại các session hết hạn và bản ghi khóa đã hết hiệu lực."""
        expired_sessions = [
            token_digest
            for token_digest, record in self._sessions.items()
            if record.expires_at <= now
        ]
        for token_digest in expired_sessions:
            self._sessions.pop(token_digest, None)

        expired_blocks = [
            client_id
            for client_id, blocked_until in self._blocked_until.items()
            if blocked_until <= now
        ]
        for client_id in expired_blocks:
            self._blocked_until.pop(client_id, None)

    # ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _token_digest(token: str) -> str:
        """Băm token trước khi dùng làm khóa trong session store."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


auth_service = AuthService()
