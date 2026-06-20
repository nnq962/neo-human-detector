import cv2
import numpy as np

# ─────────────────────────────────────────────────────────────────────────────


def ensure_bgr(frame: np.ndarray) -> np.ndarray:
    """Chuẩn hóa frame về 3-channel BGR; reject shape/channel không hợp lệ.

    Cho phép: grayscale (H,W) hoặc (H,W,1), BGR (H,W,3), BGRA (H,W,4).
    Reject: không phải ndarray, ndim ∉ {2,3}, hoặc channel ∉ {1,3,4}.
    """
    if not isinstance(frame, np.ndarray):
        raise TypeError(f"Frame phải là numpy.ndarray, nhận {type(frame).__name__}.")

    if frame.ndim == 2:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

    if frame.ndim != 3:
        raise ValueError(f"Frame phải có 2 hoặc 3 chiều, nhận shape {frame.shape}.")

    channels = frame.shape[2]
    if channels == 1:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    if channels == 3:
        return frame
    if channels == 4:
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

    raise ValueError(f"Frame phải có 1, 3 hoặc 4 channel, nhận {channels}.")


# ─────────────────────────────────────────────────────────────────────────────


def open_capture(
    src,
    backend: int = cv2.CAP_ANY,
    open_timeout_ms: int | None = None,
    read_timeout_ms: int | None = None,
) -> cv2.VideoCapture:
    """Tạo cv2.VideoCapture có open/read timeout để chống treo vô hạn khi nguồn lỗi.

    Dùng overload params của OpenCV; build không hỗ trợ thì fallback constructor thường.
    Lưu ý: nhiều backend webcam (USB) có thể bỏ qua timeout — đây là best-effort.
    """
    params: list[int] = []
    if open_timeout_ms is not None and hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
        params += [int(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC), int(open_timeout_ms)]
    if read_timeout_ms is not None and hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
        params += [int(cv2.CAP_PROP_READ_TIMEOUT_MSEC), int(read_timeout_ms)]
    if params:
        try:
            return cv2.VideoCapture(src, backend, params)
        except (TypeError, cv2.error):
            pass  # build OpenCV không hỗ trợ overload params → fallback
    return cv2.VideoCapture(src, backend)
