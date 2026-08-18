"""Đặt mật khẩu giao diện quản trị trong cấu hình YAML."""

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
        description="Lưu mật khẩu quản trị vào configs/default.yaml.",
    )
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Đọc đúng một dòng password từ standard input.",
    )
    return parser.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
def read_password(*, password_stdin: bool) -> str:
    """Đọc password an toàn và xác nhận lại khi chạy tương tác."""
    if password_stdin:
        return sys.stdin.readline().rstrip("\r\n")

    while True:
        password = getpass.getpass("Mật khẩu quản trị mới (ít nhất 8 ký tự): ")
        if not password:
            print("Lỗi: Mật khẩu không được để trống.", file=sys.stderr)
            continue
        if len(password) < MIN_PASSWORD_LENGTH:
            print(
                f"Lỗi: Mật khẩu phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự.",
                file=sys.stderr,
            )
            continue

        confirmation = getpass.getpass("Nhập lại mật khẩu: ")
        if password != confirmation:
            print("Lỗi: Hai lần nhập mật khẩu không khớp.", file=sys.stderr)
            continue
        return password


# ─────────────────────────────────────────────────────────────────────────────
def save_password(password: str) -> None:
    """Ghi mật khẩu vào config bằng cơ chế khóa và atomic hiện có."""
    from api.services import config_store

    if not password:
        raise ValueError("Mật khẩu không được để trống.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Mật khẩu phải có ít nhất {MIN_PASSWORD_LENGTH} ký tự."
        )

    def mutate(config: dict) -> None:
        """Cập nhật riêng nhánh web.auth mà không làm mất cấu hình khác."""
        web_config = config.setdefault("web", {})
        auth_config = web_config.setdefault("auth", {})
        auth_config["enabled"] = True
        auth_config["password"] = password
        auth_config.pop("password_hash", None)
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
        save_password(password)
    except (EOFError, ValueError) as error:
        print(f"Lỗi: {error}", file=sys.stderr)
        return 1

    print("Đã cập nhật web.auth.password trong configs/default.yaml.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
