"""
Wrapper YOLO cho tầng detection.

Class trong file này chỉ chịu trách nhiệm:
- Resolve và load model YOLO.
- Tạo stream inference.
- Parse result của YOLO thành `DetectionFrame`.
- Cleanup tài nguyên stream/predictor khi runtime dừng.

Các quyết định nghiệp vụ như zone occupied, UART, WebSocket không nằm ở đây.
"""

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

from ultralytics import YOLO

from src.detection.detections import DetectionFrame, parse_yolo_boxes
from src.detection.model_registry import resolve_model_path


# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class YoloDetectorConfig:
    """
    Cấu hình tối thiểu để chạy YOLO detection.

    `mode="person"` sẽ filter class người theo COCO class id 0.
    `mode="head"` dùng model custom nên không filter class.
    """

    source: str = "configs/rtsp.streams"
    mode: str = "head"
    model_size: str = "nano"
    batch_size: int = 1
    conf: float = 0.5
    vid_stride: int = 1
    stream: bool = True
    tracker: str = "bytetrack.yaml"
    persist: bool = True
    verbose: bool = False


# -----------------------------------------------------------------------------
class YoloDetector:
    """
    Adapter mỏng bao quanh Ultralytics YOLO.

    Runtime mới nên dùng class này thay vì gọi `YOLO(...).predict(...)` trực tiếp.
    Nhờ đó nếu sau này đổi backend inference, phần còn lại của pipeline ít bị ảnh hưởng.
    """

    def __init__(self, config: YoloDetectorConfig):
        self.config = config
        self.model_path = resolve_model_path(
            config.mode,
            config.model_size,
            config.batch_size,
        )
        self.model = self._load_model()
        self._results_gen: Optional[Iterable[Any]] = None

    def predict_stream(self) -> Iterable[DetectionFrame]:
        """
        Chạy inference dạng generator và yield `DetectionFrame`.

        Ultralytics có thể trả result đã flatten theo batch stream. Runtime bên ngoài
        sẽ quyết định result index tương ứng camera nào, giống logic detector cũ.
        """
        self._results_gen = self.model.predict(**self._build_predict_kwargs())

        for frame_index, result in enumerate(self._results_gen):
            resolution = self._extract_resolution(result)
            detections = parse_yolo_boxes(getattr(result, "boxes", None))

            yield DetectionFrame(
                detections=detections,
                resolution=resolution,
                frame_index=frame_index,
                raw_result=result,
            )

    def track_stream(self) -> Iterable[DetectionFrame]:
        """
        Chạy YOLO tracking bằng tracker built-in của Ultralytics.

        Mặc định class này dùng ByteTrack qua `tracker="bytetrack.yaml"`.
        Detection trả ra sẽ có thêm `track_id` nếu Ultralytics gán được ID.
        """
        self._results_gen = self.model.track(**self._build_track_kwargs())

        for frame_index, result in enumerate(self._results_gen):
            resolution = self._extract_resolution(result)
            detections = parse_yolo_boxes(getattr(result, "boxes", None))

            yield DetectionFrame(
                detections=detections,
                resolution=resolution,
                frame_index=frame_index,
                raw_result=result,
            )

    def close(self) -> None:
        """
        Dọn tài nguyên YOLO/Ultralytics.

        Đây là phần được tách từ detector cũ để tránh RTSP reader thread tiếp tục
        chạy sau khi user bấm stop.
        """
        self._close_results_generator()
        self._close_predictor_dataset()

    def _load_model(self) -> YOLO:
        """Load model YOLO theo đường dẫn đã resolve."""
        return YOLO(self.model_path, task="detect")

    def _build_predict_kwargs(self) -> Dict[str, Any]:
        """Tạo predict kwargs đồng nhất cho Ultralytics."""
        predict_kwargs: Dict[str, Any] = {
            "source": self.config.source,
            "conf": self.config.conf,
            "show": False,
            "stream": self.config.stream,
            "verbose": False,
            "vid_stride": self.config.vid_stride,
            "batch": self.config.batch_size,
        }

        # COCO person class = 0. Model head custom không cần filter class.
        if self.config.mode == "person":
            predict_kwargs["classes"] = [0]

        return predict_kwargs

    def _build_track_kwargs(self) -> Dict[str, Any]:
        """Tạo track kwargs đồng nhất cho Ultralytics ByteTrack."""
        track_kwargs = self._build_predict_kwargs()
        track_kwargs["tracker"] = self.config.tracker
        track_kwargs["persist"] = self.config.persist

        return track_kwargs

    @staticmethod
    def _extract_resolution(result: Any) -> Optional[Tuple[int, int]]:
        """Lấy resolution gốc từ result YOLO theo format (width, height)."""
        orig_img = getattr(result, "orig_img", None)
        if orig_img is None or not hasattr(orig_img, "shape"):
            return None

        height, width = orig_img.shape[:2]
        return int(width), int(height)

    def _close_results_generator(self) -> None:
        """Đóng generator predict nếu Ultralytics expose `.close()`."""
        if self._results_gen is None or not hasattr(self._results_gen, "close"):
            self._results_gen = None
            return

        try:
            self._results_gen.close()
        except Exception:
            # Cleanup không nên làm crash flow stop của runtime.
            pass
        finally:
            self._results_gen = None

    def _close_predictor_dataset(self) -> None:
        """Dừng dataset/reader threads nằm bên trong predictor của Ultralytics."""
        predictor = getattr(self.model, "predictor", None)
        if predictor is None:
            return

        dataset = getattr(predictor, "dataset", None)
        if dataset is not None:
            self._close_dataset(dataset)

        try:
            self.model.predictor = None
        except Exception:
            pass

    @staticmethod
    def _close_dataset(dataset: Any) -> None:
        """Release dataset stream, thread và VideoCapture nếu các field này tồn tại."""
        try:
            if hasattr(dataset, "running"):
                dataset.running = False

            if hasattr(dataset, "threads"):
                for thread in dataset.threads:
                    if thread.is_alive():
                        thread.join(timeout=3)

            if hasattr(dataset, "caps"):
                for cap in dataset.caps:
                    if cap and cap.isOpened():
                        cap.release()

            if hasattr(dataset, "close"):
                dataset.close()
        except Exception:
            pass


# -----------------------------------------------------------------------------
def build_yolo_detector_config(
    source: str = "configs/rtsp.streams",
    mode: str = "head",
    model_size: str = "nano",
    batch_size: int = 1,
    conf: float = 0.5,
    vid_stride: int = 1,
    tracker: str = "bytetrack.yaml",
    persist: bool = True,
    verbose: bool = False,
) -> YoloDetectorConfig:
    """Factory nhỏ để tạo config từ dict/service mà không lộ dataclass ra quá nhiều."""
    return YoloDetectorConfig(
        source=source,
        mode=mode,
        model_size=model_size,
        batch_size=int(batch_size),
        conf=float(conf),
        vid_stride=int(vid_stride),
        tracker=tracker,
        persist=bool(persist),
        verbose=bool(verbose),
    )
