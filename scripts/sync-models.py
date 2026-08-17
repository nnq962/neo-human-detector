#!/usr/bin/env python3
"""Đồng bộ model được khai báo trong configs/weights.yaml."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import platform
import sys
from typing import Any

import gdown
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "configs" / "weights.yaml"
DEFAULT_WEIGHTS_ROOT = PROJECT_ROOT / "weights"
BUFFER_SIZE = 1024 * 1024


# ─────────────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    """Đọc tham số dòng lệnh của công cụ đồng bộ model."""
    parser = argparse.ArgumentParser(
        description="Tải và kiểm tra model theo configs/weights.yaml.",
    )
    parser.add_argument(
        "--platform",
        help="Nền tảng cần đồng bộ, ví dụ pc-x86_64, jetson-aarch64 hoặc rk3588.",
    )
    parser.add_argument(
        "--model-id",
        action="append",
        default=[],
        help="Chỉ đồng bộ model ID này; có thể truyền nhiều lần.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Đường dẫn đến manifest model.",
    )
    parser.add_argument(
        "--weights-root",
        type=Path,
        default=DEFAULT_WEIGHTS_ROOT,
        help="Thư mục đích chứa model.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Chỉ kiểm tra, không tải model còn thiếu.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Tải lại model có checksum không đúng.",
    )
    return parser.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
def detect_platform() -> str:
    """Tự nhận diện tên nền tảng từ kiến trúc và device tree."""
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "pc-x86_64"

    if machine in {"aarch64", "arm64"}:
        device_description = _read_device_description()
        if "rk3588" in device_description:
            return "rk3588"
        if any(name in device_description for name in ("jetson", "nvidia", "tegra")):
            return "jetson-aarch64"

    raise RuntimeError(
        "Không tự nhận diện được nền tảng. Hãy truyền --platform thủ công.",
    )


# ─────────────────────────────────────────────────────────────────────────────
def load_manifest(path: Path) -> list[dict[str, Any]]:
    """Đọc và kiểm tra cấu trúc cơ bản của manifest model."""
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy manifest: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Manifest phải có schema_version: 1.")

    models = data.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("Manifest phải chứa danh sách models không rỗng.")

    required_fields = {"id", "path", "platforms", "sha256", "drive_id"}
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for index, model in enumerate(models, start=1):
        if not isinstance(model, dict):
            raise ValueError(f"Model thứ {index} không phải mapping YAML.")

        missing_fields = required_fields - model.keys()
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(f"Model thứ {index} thiếu trường: {missing}.")

        model_id = str(model["id"])
        model_path = str(model["path"])
        if model_id in seen_ids:
            raise ValueError(f"Model ID bị trùng: {model_id}")
        if model_path in seen_paths:
            raise ValueError(f"Đường dẫn model bị trùng: {model_path}")
        if not _is_sha256(str(model["sha256"])):
            raise ValueError(f"SHA-256 không hợp lệ cho model: {model_id}")
        if not isinstance(model["platforms"], list) or not model["platforms"]:
            raise ValueError(f"platforms không hợp lệ cho model: {model_id}")

        seen_ids.add(model_id)
        seen_paths.add(model_path)

    return models


# ─────────────────────────────────────────────────────────────────────────────
def select_models(
    models: list[dict[str, Any]],
    *,
    target_platform: str,
    requested_ids: list[str],
) -> list[dict[str, Any]]:
    """Lọc model theo nền tảng và danh sách ID được yêu cầu."""
    requested = set(requested_ids)
    known_ids = {str(model["id"]) for model in models}
    unknown_ids = requested - known_ids
    if unknown_ids:
        unknown = ", ".join(sorted(unknown_ids))
        raise ValueError(f"Không tìm thấy model ID trong manifest: {unknown}")

    selected = [
        model
        for model in models
        if target_platform in model["platforms"]
        and (not requested or str(model["id"]) in requested)
    ]
    if not selected:
        raise ValueError(f"Không có model nào dành cho platform {target_platform}.")
    return selected


# ─────────────────────────────────────────────────────────────────────────────
def sync_models(
    models: list[dict[str, Any]],
    *,
    weights_root: Path,
    check_only: bool,
    force: bool,
) -> bool:
    """Kiểm tra và tải các model đã chọn, trả về True khi tất cả hợp lệ."""
    all_valid = True
    for model in models:
        model_id = str(model["id"])
        target = _safe_target_path(weights_root, str(model["path"]))
        expected_sha256 = str(model["sha256"]).lower()

        if target.is_file() and calculate_sha256(target) == expected_sha256:
            print(f"[OK] {model_id}")
            continue

        if target.exists() and not target.is_file():
            print(f"[LỖI] Đường dẫn đích không phải file: {target}", file=sys.stderr)
            all_valid = False
            continue

        if target.is_file() and not force:
            print(
                f"[LỖI] Checksum sai: {model_id}. "
                "Dùng --force nếu muốn tải lại.",
                file=sys.stderr,
            )
            all_valid = False
            continue

        if check_only:
            print(f"[THIẾU] {model_id}: {target}", file=sys.stderr)
            all_valid = False
            continue

        drive_id = model.get("drive_id")
        if not isinstance(drive_id, str) or not drive_id.strip():
            print(
                f"[LỖI] Chưa cấu hình drive_id cho model: {model_id}",
                file=sys.stderr,
            )
            all_valid = False
            continue

        try:
            _download_model(
                drive_id=drive_id.strip(),
                target=target,
                expected_sha256=expected_sha256,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"[LỖI] {model_id}: {exc}", file=sys.stderr)
            all_valid = False
            continue

        print(f"[ĐÃ TẢI] {model_id}")

    return all_valid


# ─────────────────────────────────────────────────────────────────────────────
def calculate_sha256(path: Path) -> str:
    """Tính checksum SHA-256 của một file theo từng khối."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(BUFFER_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    """Chạy quy trình đồng bộ model và trả mã thoát phù hợp."""
    args = parse_args()
    try:
        target_platform = args.platform or detect_platform()
        models = load_manifest(args.manifest.resolve())
        selected = select_models(
            models,
            target_platform=target_platform,
            requested_ids=args.model_id,
        )
        print(
            f"Đồng bộ {len(selected)} model cho platform {target_platform} "
            f"vào {args.weights_root.resolve()}",
        )
        success = sync_models(
            selected,
            weights_root=args.weights_root.resolve(),
            check_only=args.check,
            force=args.force,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"[LỖI] {exc}", file=sys.stderr)
        return 1

    return 0 if success else 1


# ─────────────────────────────────────────────────────────────────────────────
def _read_device_description() -> str:
    """Đọc chuỗi mô tả phần cứng từ device tree nếu tồn tại."""
    descriptions: list[str] = []
    for path in (
        Path("/proc/device-tree/model"),
        Path("/proc/device-tree/compatible"),
    ):
        try:
            descriptions.append(path.read_bytes().replace(b"\x00", b" ").decode())
        except (OSError, UnicodeDecodeError):
            continue
    return " ".join(descriptions).lower()


# ─────────────────────────────────────────────────────────────────────────────
def _safe_target_path(weights_root: Path, relative_path: str) -> Path:
    """Tạo đường dẫn đích và ngăn manifest thoát khỏi thư mục weights."""
    root = weights_root.resolve()
    relative = Path(relative_path)
    if relative.is_absolute():
        raise ValueError(f"Đường dẫn model không được là tuyệt đối: {relative_path}")

    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError(f"Đường dẫn model không an toàn: {relative_path}")
    return target


# ─────────────────────────────────────────────────────────────────────────────
def _download_model(
    *,
    drive_id: str,
    target: Path,
    expected_sha256: str,
) -> None:
    """Tải model vào file tạm, xác minh rồi thay thế file đích."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.part")
    temporary.unlink(missing_ok=True)

    try:
        downloaded = gdown.download(
            id=drive_id,
            output=str(temporary),
            quiet=False,
        )
        if downloaded is None or not temporary.is_file():
            raise RuntimeError("Google Drive không trả về file model.")

        actual_sha256 = calculate_sha256(temporary)
        if actual_sha256 != expected_sha256:
            raise ValueError(
                "Checksum không đúng "
                f"(mong đợi {expected_sha256}, nhận {actual_sha256}).",
            )

        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
def _is_sha256(value: str) -> bool:
    """Kiểm tra chuỗi có đúng định dạng SHA-256 hay không."""
    return len(value) == 64 and all(
        character in "0123456789abcdefABCDEF" for character in value
    )


if __name__ == "__main__":
    raise SystemExit(main())
