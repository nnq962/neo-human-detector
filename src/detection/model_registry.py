"""
Registry model detection.

File này gom toàn bộ mapping giữa cấu hình nghiệp vụ và đường dẫn model thật.
Nhờ vậy API/service có thể validate cấu hình mà không cần import runtime YOLO.
"""

from typing import Dict, Literal, Tuple


ModelSize = Literal["nano", "medium"]
ModelTask = Literal["detect", "pose"]
ModelKey  = Tuple[str, str, int]   # (model_size, task, batch_size)


MODEL_PATHS: Dict[ModelKey, str] = {
    ("nano", "detect", 1): "weights/person/yolo26n.pt",
    ("nano", "detect", 2): "weights/person/yolo26n.pt",
    ("nano", "pose",   1): "weights/person/yolo26m-pose.pt",
    ("nano", "pose",   2): "weights/person/yolo26m-pose.pt",
}


# ─────────────────────────────────────────────────────────────────────────────
def resolve_model_path(model_size: str, task: str, batch_size: int) -> str:
    """Nguồn sự thật duy nhất cho mapping (model_size, task, batch_size) → path."""
    model_key = (model_size, task, int(batch_size))
    model_path = MODEL_PATHS.get(model_key)

    if model_path is None:
        raise ValueError(_build_unsupported_model_message(model_size, task, batch_size))

    return model_path


# ─────────────────────────────────────────────────────────────────────────────
def validate_model_config(model_size: str, task: str, batch_size: int) -> None:
    """Validate cấu hình model và raise ValueError nếu chưa được hỗ trợ."""
    resolve_model_path(model_size, task, batch_size)


# ─────────────────────────────────────────────────────────────────────────────
def supported_model_configs() -> Tuple[ModelKey, ...]:
    """Trả danh sách cấu hình model đang hỗ trợ, dùng cho API hoặc log."""
    return tuple(sorted(MODEL_PATHS))


# ─────────────────────────────────────────────────────────────────────────────
def _build_unsupported_model_message(model_size: str, task: str, batch_size: int) -> str:
    supported = ", ".join(
        f"{s}/{t}/batch{b}"
        for s, t, b in supported_model_configs()
    )
    return (
        f"Unsupported model_size/task/batch_size: "
        f"{model_size}/{task}/batch{int(batch_size)}. Supported: {supported}"
    )
