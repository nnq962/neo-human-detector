"""Đặt password hash cho giao diện quản trị trong cấu hình YAML."""

from __future__ import annotations

import argparse
import getpass
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MIN_PASSWORD_LENGTH = 8


# ─────────────────────────────────────────────────────────────────────────────
def parse_arguments() -> argparse.Namespace:
    """Đọc tùy chọn nhận password từ terminal hoặc standard input."""
    parser = argparse.ArgumentParser(
        description="Băm và lưu mật khẩu quản trị vào configs/default.yaml.",
    )
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Đọc đúng một dòng password từ standard input.",
    )
    parser.add_argument(
        "--migrate-legacy",
        action="store_true",
        help="Cho phép giữ mật khẩu frontend cũ ngắn hơn chuẩn mới.",
    )
    return parser.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
def read_password(*, password_stdin: bool) -> str:
    """Đọc password an toàn và xác nhận lại khi chạy tương tác."""
    if password_stdin:
        return sys.stdin.readline().rstrip("\r\n")

    password = getpass.getpass("Mật khẩu quản trị mới: ")
    confirmation = getpass.getpass("Nhập lại mật khẩu: ")
    if password != confirmation:
        raise ValueError("Hai lần nhập mật khẩu không khớp.")
    return password


# ─────────────────────────────────────────────────────────────────────────────
def save_password_hash(password: str, *, allow_short: bool = False) -> None:
    """Băm password và ghi vào config bằng cơ chế khóa/atomic hiện có."""
    from api.services import config_store
    from api.services.auth import hash_password

    if not password:
        raise ValueError("Mật khẩu không được để trống.")
    if len(password) < MIN_PASSWORD_LENGTH and not allow_short:
        raise ValueError(
            f"Mật khẩu phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự."
        )
    encoded_hash = hash_password(password)

    def mutate(config: dict) -> None:
        """Cập nhật riêng nhánh web.auth mà không làm mất cấu hình khác."""
        web_config = config.setdefault("web", {})
        auth_config = web_config.setdefault("auth", {})
        auth_config["enabled"] = True
        auth_config["password_hash"] = encoded_hash
        auth_config.setdefault("session_ttl_seconds", 28800)
        auth_config.setdefault("max_login_failures", 5)
        auth_config.setdefault("login_window_seconds", 60)
        auth_config.setdefault("login_block_seconds", 300)

    config_store.update_config_data(mutate)


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    """Thực thi công cụ và chỉ in thông tin không nhạy cảm."""
    arguments = parse_arguments()
    try:
        password = read_password(password_stdin=arguments.password_stdin)
        save_password_hash(password, allow_short=arguments.migrate_legacy)
    except (EOFError, ValueError) as error:
        print(f"Lỗi: {error}", file=sys.stderr)
        return 1

    print("Đã cập nhật web.auth.password_hash trong configs/default.yaml.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
