#!/usr/bin/env python3
"""Đồng bộ artifact cần thiết trước khi cài project."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import sys
from typing import Any

import gdown
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "configs" / "artifacts.yaml"
BUFFER_SIZE = 1024 * 1024


# ─────────────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    """Đọc tham số dòng lệnh của công cụ đồng bộ artifact."""
    parser = argparse.ArgumentParser(
        description="Tải artifact theo configs/artifacts.yaml.",
    )
    parser.add_argument("--platform", required=True, help="Nền tảng cần đồng bộ.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Đường dẫn đến manifest artifact.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Thư mục gốc dùng để phân giải path artifact.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Chỉ kiểm tra, không tải artifact còn thiếu.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Tải lại artifact có checksum không đúng.",
    )
    return parser.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
def load_artifacts(path: Path) -> list[dict[str, Any]]:
    """Đọc và kiểm tra manifest artifact."""
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy manifest: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Manifest artifact phải có schema_version: 1.")

    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("Manifest phải chứa danh sách artifacts không rỗng.")

    required_fields = {"id", "path", "platforms", "sha256", "drive_id"}
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for index, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, dict):
            raise ValueError(f"Artifact thứ {index} không phải mapping YAML.")

        missing_fields = required_fields - artifact.keys()
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(f"Artifact thứ {index} thiếu trường: {missing}.")

        artifact_id = str(artifact["id"])
        artifact_path = str(artifact["path"])
        if artifact_id in seen_ids:
            raise ValueError(f"Artifact ID bị trùng: {artifact_id}")
        if artifact_path in seen_paths:
            raise ValueError(f"Đường dẫn artifact bị trùng: {artifact_path}")
        if not _is_sha256(str(artifact["sha256"])):
            raise ValueError(f"SHA-256 không hợp lệ: {artifact_id}")
        if not isinstance(artifact["platforms"], list) or not artifact["platforms"]:
            raise ValueError(f"platforms không hợp lệ: {artifact_id}")

        seen_ids.add(artifact_id)
        seen_paths.add(artifact_path)
    return artifacts


# ─────────────────────────────────────────────────────────────────────────────
def sync_artifacts(
    artifacts: list[dict[str, Any]],
    *,
    platform_name: str,
    project_root: Path,
    check_only: bool,
    force: bool,
) -> bool:
    """Kiểm tra và tải artifact dành cho nền tảng đã chọn."""
    selected = [
        artifact
        for artifact in artifacts
        if platform_name in artifact["platforms"]
    ]
    if not selected:
        raise ValueError(f"Không có artifact cho platform {platform_name}.")

    all_valid = True
    for artifact in selected:
        artifact_id = str(artifact["id"])
        target = _safe_target_path(project_root, str(artifact["path"]))
        expected_sha256 = str(artifact["sha256"]).lower()

        if target.is_file() and calculate_sha256(target) == expected_sha256:
            print(f"[OK] {artifact_id}")
            continue

        if target.exists() and not target.is_file():
            print(f"[LỖI] Đích không phải file: {target}", file=sys.stderr)
            all_valid = False
            continue

        if target.is_file() and not force:
            print(
                f"[LỖI] Checksum sai: {artifact_id}. Dùng --force để tải lại.",
                file=sys.stderr,
            )
            all_valid = False
            continue

        if check_only:
            print(f"[THIẾU] {artifact_id}: {target}", file=sys.stderr)
            all_valid = False
            continue

        drive_id = artifact.get("drive_id")
        if not isinstance(drive_id, str) or not drive_id.strip():
            print(f"[LỖI] Chưa có drive_id: {artifact_id}", file=sys.stderr)
            all_valid = False
            continue

        try:
            _download_artifact(
                drive_id=drive_id.strip(),
                target=target,
                expected_sha256=expected_sha256,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"[LỖI] {artifact_id}: {exc}", file=sys.stderr)
            all_valid = False
            continue

        print(f"[ĐÃ TẢI] {artifact_id}")

    return all_valid


# ─────────────────────────────────────────────────────────────────────────────
def calculate_sha256(path: Path) -> str:
    """Tính SHA-256 của file theo từng khối."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(BUFFER_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    """Chạy đồng bộ artifact và trả mã thoát phù hợp."""
    args = parse_args()
    try:
        artifacts = load_artifacts(args.manifest.resolve())
        success = sync_artifacts(
            artifacts,
            platform_name=args.platform,
            project_root=args.project_root.resolve(),
            check_only=args.check,
            force=args.force,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"[LỖI] {exc}", file=sys.stderr)
        return 1
    return 0 if success else 1


# ─────────────────────────────────────────────────────────────────────────────
def _safe_target_path(project_root: Path, relative_path: str) -> Path:
    """Phân giải đường dẫn đích và ngăn path traversal."""
    root = project_root.resolve()
    relative = Path(relative_path)
    if relative.is_absolute():
        raise ValueError(f"Đường dẫn artifact không được tuyệt đối: {relative_path}")

    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError(f"Đường dẫn artifact không an toàn: {relative_path}")
    return target


# ─────────────────────────────────────────────────────────────────────────────
def _download_artifact(
    *,
    drive_id: str,
    target: Path,
    expected_sha256: str,
) -> None:
    """Tải artifact vào file tạm, xác minh rồi thay thế file đích."""
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
            raise RuntimeError("Google Drive không trả về artifact.")

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
