"""
Registry model detection.

File này gom toàn bộ mapping giữa cấu hình nghiệp vụ và đường dẫn model thật.
Nhờ vậy API/service có thể validate cấu hình mà không cần import runtime YOLO.
"""

from typing import Dict, Literal, Tuple


DetectionMode = Literal["head", "person"]
ModelSize = Literal["nano", "medium"]
ModelKey = Tuple[str, str, int]


MODEL_PATHS: Dict[ModelKey, str] = {
    ("head", "nano", 1): "weights/head/yolo8n_rknn_model_b1",
    ("head", "nano", 2): "weights/head/yolo8n_rknn_model_b2",
    ("head", "nano", 4): "weights/head/yolo8n_rknn_model_b4",
    ("head", "nano", 8): "weights/head/yolo8n_rknn_model_b8",
    ("head", "medium", 1): "weights/head/yolo8m_rknn_model_b1",
    ("head", "medium", 2): "weights/head/yolo8m_rknn_model_b2",
    ("person", "nano", 1): "weights/person/yolo26n.pt",
    ("person", "medium", 1): "weights/person/yolo11m_rknn_model",
}


# -----------------------------------------------------------------------------
def resolve_model_path(mode: str, model_size: str, batch_size: int) -> str:
    """
    Trả về đường dẫn model tương ứng với cấu hình detector.

    Hàm này là nguồn sự thật duy nhất cho mapping model. Nếu sau này thêm RKNN
    batch mới hoặc model khác, chỉ cần cập nhật `MODEL_PATHS`.
    """
    model_key = (mode, model_size, int(batch_size))
    model_path = MODEL_PATHS.get(model_key)

    if model_path is None:
        raise ValueError(_build_unsupported_model_message(mode, model_size, batch_size))

    return model_path


# -----------------------------------------------------------------------------
def validate_model_config(mode: str, model_size: str, batch_size: int) -> None:
    """Validate cấu hình model và raise ValueError nếu chưa được hỗ trợ."""
    resolve_model_path(mode, model_size, batch_size)


# -----------------------------------------------------------------------------
def supported_model_configs() -> Tuple[ModelKey, ...]:
    """Trả danh sách cấu hình model đang hỗ trợ, dùng cho API hoặc log."""
    return tuple(sorted(MODEL_PATHS))


# -----------------------------------------------------------------------------
def _build_unsupported_model_message(mode: str, model_size: str, batch_size: int) -> str:
    """Tạo message lỗi đồng nhất khi cấu hình model không tồn tại."""
    supported = ", ".join(
        f"{supported_mode}/{supported_size}/batch{supported_batch}"
        for supported_mode, supported_size, supported_batch in supported_model_configs()
    )

    return (
        "Unsupported mode/model_size/batch_size: "
        f"{mode}/{model_size}/batch{int(batch_size)}. Supported: {supported}"
    )
