"""Kiểm thử catalog model đọc từ manifest."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.model_catalog import (
    find_default_model,
    find_legacy_detection_model,
    list_models,
    model_id_from_path,
    resolve_model,
    resolve_model_path,
)


# ─────────────────────────────────────────────────────────────────────────────
def _touch(root: Path, relative_path: str) -> None:
    """Tạo một file model rỗng phục vụ kiểm thử."""
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


# ─────────────────────────────────────────────────────────────────────────────
def _entry(
    model_id: str,
    path: str,
    *,
    kind: str = "detection",
    version: str = "yolo26",
    task: str | None = "detect",
    variant: str | None = "nano",
    runtime_supported: bool = True,
) -> dict:
    """Tạo một khai báo model tối thiểu hợp lệ cho kiểm thử."""
    return {
        "id": model_id,
        "kind": kind,
        "backend": "pytorch",
        "version": version,
        "task": task,
        "variant": variant,
        "platforms": ["pc-x86_64"],
        "batch_size": "dynamic",
        "path": path,
        "runtime_supported": runtime_supported,
    }


# ─────────────────────────────────────────────────────────────────────────────
def _write_manifest(root: Path, entries: list[dict]) -> Path:
    """Ghi manifest tạm và trả đường dẫn của nó."""
    manifest = root / "weights.yaml"
    manifest.write_text(
        yaml.safe_dump({"schema_version": 1, "models": entries}),
        encoding="utf-8",
    )
    return manifest


# ─────────────────────────────────────────────────────────────────────────────
def test_catalog_only_lists_installed_supported_models(tmp_path: Path) -> None:
    """Catalog chỉ trả model đã tồn tại và được runtime hỗ trợ."""
    installed_path = "pytorch/yolo/yolo26/detect/yolo26n.pt"
    _touch(tmp_path, installed_path)
    manifest = _write_manifest(
        tmp_path,
        [
            _entry("installed", installed_path),
            _entry("missing", "pytorch/yolo/yolo26/detect/missing.pt"),
            _entry(
                "unsupported",
                "rknn/rk3588/yolo26n.rknn",
                runtime_supported=False,
            ),
        ],
    )

    models = list_models(weights_root=tmp_path, manifest_path=manifest)

    assert [model.id for model in models] == ["installed"]
    assert models[0].version == "yolo26"
    assert models[0].platforms == ("pc-x86_64",)


# ─────────────────────────────────────────────────────────────────────────────
def test_legacy_detection_selection_prefers_yolo26(tmp_path: Path) -> None:
    """Migration config cũ phải ưu tiên YOLO26 khi có nhiều version."""
    yolo11_path = "pytorch/yolo/yolo11/detect/yolo11n.pt"
    yolo26_path = "pytorch/yolo/yolo26/detect/yolo26n.pt"
    _touch(tmp_path, yolo11_path)
    _touch(tmp_path, yolo26_path)
    manifest = _write_manifest(
        tmp_path,
        [
            _entry("yolo11n", yolo11_path, version="yolo11"),
            _entry("yolo26n", yolo26_path),
        ],
    )

    model_id = find_legacy_detection_model(
        "detect",
        "nano",
        tmp_path,
        manifest,
    )

    assert model_id == "yolo26n"


# ─────────────────────────────────────────────────────────────────────────────
def test_default_detection_prefers_medium_pose_yolo26(tmp_path: Path) -> None:
    """Model mặc định detection phải ưu tiên YOLO26 pose medium."""
    detect_path = "pytorch/yolo/yolo26/detect/yolo26n.pt"
    pose_path = "pytorch/yolo/yolo26/pose/yolo26m-pose.pt"
    _touch(tmp_path, detect_path)
    _touch(tmp_path, pose_path)
    manifest = _write_manifest(
        tmp_path,
        [
            _entry("yolo26n-detect", detect_path),
            _entry(
                "yolo26m-pose",
                pose_path,
                task="pose",
                variant="medium",
            ),
        ],
    )

    assert (
        find_default_model("detection", tmp_path, manifest)
        == "yolo26m-pose"
    )


# ─────────────────────────────────────────────────────────────────────────────
def test_resolve_model_supports_legacy_path_alias(tmp_path: Path) -> None:
    """Resolver phải nhận cả ID mới lẫn đường dẫn model trong config cũ."""
    relative_path = "pytorch/yolo/yolo26/pose/yolo26m-pose.pt"
    _touch(tmp_path, relative_path)
    manifest = _write_manifest(
        tmp_path,
        [
            _entry(
                "yolo26m-pose-pytorch",
                relative_path,
                task="pose",
                variant="medium",
            ),
        ],
    )

    resolved = resolve_model(
        relative_path,
        weights_root=tmp_path,
        manifest_path=manifest,
    )

    assert resolved.id == "yolo26m-pose-pytorch"
    assert (
        model_id_from_path(
            f"weights/{relative_path}",
            weights_root=tmp_path,
            manifest_path=manifest,
        )
        == "yolo26m-pose-pytorch"
    )


# ─────────────────────────────────────────────────────────────────────────────
def test_resolve_model_rejects_missing_or_traversal_id(tmp_path: Path) -> None:
    """Resolver không chấp nhận model thiếu hoặc model ID path traversal."""
    relative_path = "pytorch/yolo/yolo26/detect/yolo26n.pt"
    _touch(tmp_path, relative_path)
    manifest = _write_manifest(
        tmp_path,
        [_entry("yolo26n", relative_path)],
    )

    with pytest.raises(FileNotFoundError):
        resolve_model(
            "missing",
            weights_root=tmp_path,
            manifest_path=manifest,
        )

    with pytest.raises(ValueError):
        resolve_model(
            "../secret.pt",
            weights_root=tmp_path,
            manifest_path=manifest,
        )


# ─────────────────────────────────────────────────────────────────────────────
def test_resolve_model_path_returns_installed_file(tmp_path: Path) -> None:
    """Resolver path phải trả đúng file tuyệt đối trong weights root."""
    relative_path = "pytorch/reid/osnet_ain.pth.tar"
    _touch(tmp_path, relative_path)
    manifest = _write_manifest(
        tmp_path,
        [
            _entry(
                "osnet",
                relative_path,
                kind="reid",
                task="reid",
                variant=None,
            ),
        ],
    )

    resolved = resolve_model_path(
        "osnet",
        kind="reid",
        weights_root=tmp_path,
        manifest_path=manifest,
    )

    assert resolved == str((tmp_path / relative_path).resolve())


# ─────────────────────────────────────────────────────────────────────────────
def test_catalog_rejects_duplicate_ids_and_unsafe_paths(tmp_path: Path) -> None:
    """Catalog phải từ chối ID trùng và đường dẫn thoát khỏi weights."""
    duplicate_manifest = _write_manifest(
        tmp_path,
        [
            _entry("duplicate", "first.pt"),
            _entry("duplicate", "second.pt"),
        ],
    )
    with pytest.raises(ValueError, match="bị trùng"):
        list_models(weights_root=tmp_path, manifest_path=duplicate_manifest)

    unsafe_manifest = _write_manifest(
        tmp_path,
        [_entry("unsafe", "../outside.pt")],
    )
    with pytest.raises(ValueError, match="không an toàn"):
        list_models(weights_root=tmp_path, manifest_path=unsafe_manifest)
