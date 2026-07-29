"""Đọc catalog model từ manifest và phân giải model cho runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast

import yaml


ModelKind = Literal["detection", "reid"]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEIGHTS_ROOT = PROJECT_ROOT / "weights"
WEIGHTS_MANIFEST = PROJECT_ROOT / "configs" / "weights.yaml"


# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ModelArtifact:
    """Mô tả một model đã cài và được runtime hỗ trợ."""

    id: str
    kind: ModelKind
    backend: str
    version: str
    task: str | None
    variant: str | None
    format: str
    path: str
    platforms: tuple[str, ...]
    batch_size: int | str | None
    runtime_supported: bool

    def to_dict(self) -> dict:
        """Chuyển metadata model thành dictionary dùng cho API."""
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
def list_models(
    kind: ModelKind | None = None,
    weights_root: Path | str = WEIGHTS_ROOT,
    manifest_path: Path | str = WEIGHTS_MANIFEST,
) -> tuple[ModelArtifact, ...]:
    """Trả model đã cài từ manifest, có thể lọc theo loại."""
    root = Path(weights_root).resolve()
    entries = _load_manifest(Path(manifest_path).resolve())
    models = [
        artifact
        for entry in entries
        if (artifact := _build_installed_artifact(entry, root)) is not None
    ]
    models.sort(key=lambda model: model.id)
    if kind is None:
        return tuple(models)
    return tuple(model for model in models if model.kind == kind)


# ─────────────────────────────────────────────────────────────────────────────
def resolve_model(
    model_id: str,
    *,
    kind: ModelKind | None = None,
    weights_root: Path | str = WEIGHTS_ROOT,
    manifest_path: Path | str = WEIGHTS_MANIFEST,
) -> ModelArtifact:
    """Phân giải model ID hoặc đường dẫn config cũ thành artifact."""
    normalized_id = _normalize_model_id(model_id)
    for model in list_models(kind, weights_root, manifest_path):
        relative_path = _remove_prefix(model.path, "weights/")
        if normalized_id in {model.id, relative_path}:
            return model

    kind_label = f" {kind}" if kind else ""
    raise FileNotFoundError(f"Không tìm thấy{kind_label} model: {model_id}")


# ─────────────────────────────────────────────────────────────────────────────
def resolve_model_path(
    model_id: str,
    *,
    kind: ModelKind | None = None,
    weights_root: Path | str = WEIGHTS_ROOT,
    manifest_path: Path | str = WEIGHTS_MANIFEST,
) -> str:
    """Trả đường dẫn tuyệt đối của model đã được kiểm tra trong catalog."""
    root = Path(weights_root).resolve()
    artifact = resolve_model(
        model_id,
        kind=kind,
        weights_root=root,
        manifest_path=manifest_path,
    )
    return str(_safe_model_path(root, _remove_prefix(artifact.path, "weights/")))


# ─────────────────────────────────────────────────────────────────────────────
def model_id_from_path(
    model_path: str | Path | None,
    *,
    kind: ModelKind | None = None,
    weights_root: Path | str = WEIGHTS_ROOT,
    manifest_path: Path | str = WEIGHTS_MANIFEST,
) -> str | None:
    """Chuyển đường dẫn model trong config cũ thành model ID hiện tại."""
    if not model_path:
        return None

    value = Path(model_path).as_posix()
    if value.startswith("weights/"):
        value = _remove_prefix(value, "weights/")

    try:
        return resolve_model(
            value,
            kind=kind,
            weights_root=weights_root,
            manifest_path=manifest_path,
        ).id
    except FileNotFoundError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
def find_legacy_detection_model(
    task: str,
    model_size: str,
    weights_root: Path | str = WEIGHTS_ROOT,
    manifest_path: Path | str = WEIGHTS_MANIFEST,
) -> str | None:
    """Tìm model phù hợp với cấu hình task/model_size phiên bản cũ."""
    candidates = [
        model
        for model in list_models("detection", weights_root, manifest_path)
        if model.task == task and model.variant == model_size
    ]
    if not candidates:
        return None

    candidates.sort(key=lambda model: (model.version != "yolo26", model.id))
    return candidates[0].id


# ─────────────────────────────────────────────────────────────────────────────
def find_default_model(
    kind: ModelKind,
    weights_root: Path | str = WEIGHTS_ROOT,
    manifest_path: Path | str = WEIGHTS_MANIFEST,
) -> str | None:
    """Chọn model mặc định ổn định từ catalog đã cài."""
    models = list(list_models(kind, weights_root, manifest_path))
    if not models:
        return None

    if kind == "detection":
        models.sort(
            key=lambda model: (
                model.version != "yolo26",
                model.task != "pose",
                model.variant != "medium",
                model.id,
            ),
        )
    return models[0].id


# ─────────────────────────────────────────────────────────────────────────────
def _load_manifest(path: Path) -> list[dict[str, Any]]:
    """Đọc và kiểm tra phần khung của manifest model."""
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy model manifest: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Model manifest phải có schema_version: 1.")

    entries = data.get("models")
    if not isinstance(entries, list):
        raise ValueError("Model manifest phải chứa danh sách models.")

    models: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Model thứ {index} không phải mapping YAML.")

        model_id = str(entry.get("id", "")).strip()
        model_path = str(entry.get("path", "")).strip()
        if not model_id or model_id in seen_ids:
            raise ValueError(f"Model ID thiếu hoặc bị trùng: {model_id!r}")
        if not model_path or model_path in seen_paths:
            raise ValueError(f"Model path thiếu hoặc bị trùng: {model_path!r}")

        seen_ids.add(model_id)
        seen_paths.add(model_path)
        models.append(entry)
    return models


# ─────────────────────────────────────────────────────────────────────────────
def _build_installed_artifact(
    entry: dict[str, Any],
    root: Path,
) -> ModelArtifact | None:
    """Tạo artifact nếu model được hỗ trợ và file đã tồn tại."""
    if not bool(entry.get("runtime_supported", True)):
        return None

    kind_value = str(entry.get("kind", ""))
    if kind_value not in {"detection", "reid"}:
        raise ValueError(f"Model kind không hợp lệ: {kind_value!r}")

    relative_path = str(entry["path"])
    model_path = _safe_model_path(root, relative_path)
    if model_path.is_symlink() or not model_path.is_file():
        return None

    platforms_value = entry.get("platforms")
    if not isinstance(platforms_value, list) or not platforms_value:
        raise ValueError(f"platforms không hợp lệ cho model: {entry['id']}")

    task = entry.get("task")
    variant = entry.get("variant")
    return ModelArtifact(
        id=str(entry["id"]),
        kind=cast(ModelKind, kind_value),
        backend=str(entry.get("backend", "")),
        version=str(entry.get("version", "")),
        task=str(task) if task is not None else None,
        variant=str(variant) if variant is not None else None,
        format=_model_format(model_path.name),
        path=f"weights/{Path(relative_path).as_posix()}",
        platforms=tuple(str(value) for value in platforms_value),
        batch_size=entry.get("batch_size"),
        runtime_supported=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _safe_model_path(root: Path, relative_path: str) -> Path:
    """Phân giải đường dẫn model và ngăn path traversal khỏi weights."""
    relative = Path(relative_path)
    if relative.is_absolute():
        raise ValueError(f"Model path không được là tuyệt đối: {relative_path}")

    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(f"Model path không an toàn: {relative_path}")
    return resolved


# ─────────────────────────────────────────────────────────────────────────────
def _model_format(filename: str) -> str:
    """Lấy định dạng model, bao gồm phần mở rộng kép .pth.tar."""
    lowered = filename.lower()
    if lowered.endswith(".pth.tar"):
        return "pth.tar"
    return _remove_prefix(Path(lowered).suffix, ".")


# ─────────────────────────────────────────────────────────────────────────────
def _normalize_model_id(model_id: str) -> str:
    """Chuẩn hóa model ID và từ chối path traversal."""
    normalized = Path(model_id.strip()).as_posix()
    if normalized.startswith("weights/"):
        normalized = _remove_prefix(normalized, "weights/")
    if not normalized or normalized.startswith("../") or "/../" in normalized:
        raise ValueError(f"model_id không hợp lệ: {model_id}")
    return normalized


# ─────────────────────────────────────────────────────────────────────────────
def _remove_prefix(value: str, prefix: str) -> str:
    """Loại bỏ prefix khỏi chuỗi theo cách tương thích Python 3.8."""
    if value.startswith(prefix):
        return value[len(prefix):]
    return value
