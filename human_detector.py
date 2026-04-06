import cv2
from ultralytics import YOLO


class HumanDetector:
    """
    Phát hiện người dùng YOLO, hỗ trợ 2 mode:
        - 'person'     : Phát hiện toàn thân người (dùng model COCO, filter class=0)
        - 'human_head' : Phát hiện đầu người (dùng model head chuyên dụng)

    Source hỗ trợ:
        - int       : USB Camera (0, 1, 2, ...)
        - str RTSP  : "rtsp://user:pass@ip:port/stream"
        - str file  : "path/to/video.mp4" hoặc "path/to/image.jpg"
    """

    DEFAULT_MODELS = {
        "person":     "models/person/yolo26n.pt",
        "human_head": "models/head/yolov8_nano.pt",
    }

    def __init__(
        self,
        mode: str = "person",
        model_path: str = None,
        source=0,
        conf: float = 0.50,
        imgsz: int = 640,
        device: int = 0,
        half: bool = True,
        show: bool = True,
    ):
        """
        Args:
            mode       : 'person' hoặc 'human_head'
            model_path : Đường dẫn model .pt (None = dùng mặc định theo mode)
            source     : int (USB cam), str (file/RTSP)
            conf       : Ngưỡng confidence (0.0 - 1.0)
            imgsz      : Kích thước ảnh đầu vào
            device     : GPU index (0, 1, ...) hoặc 'cpu'
            half       : Dùng FP16 để tăng tốc (chỉ hoạt động với GPU)
            show       : Hiển thị cửa sổ kết quả
        """
        if mode not in self.DEFAULT_MODELS:
            raise ValueError(f"mode phải là 'person' hoặc 'human_head', nhận được: '{mode}'")

        self.mode = mode
        self.source = source
        self.conf = conf
        self.imgsz = imgsz
        self.device = device
        self.half = half
        self.show = show

        # Mode 'person' dùng model COCO nên cần filter class 0 (person)
        # Mode 'human_head' dùng model chuyên biệt, không cần filter
        self.classes = [0] if mode == "person" else None

        # Load model
        resolved_path = model_path or self.DEFAULT_MODELS[mode]
        print(f"[HumanDetector] Mode: {mode} | Model: {resolved_path}")
        self.model = YOLO(resolved_path)

    def run(self):
        """
        Chạy detection liên tục trên source đã cấu hình.
        Dùng YOLO stream mode — hỗ trợ mọi loại source.
        Nhấn 'q' để dừng khi show=True.
        """
        print(f"[HumanDetector] Bắt đầu từ source: {self.source} | Nhấn 'q' để thoát.")

        results = self.model.predict(
            source=self.source,
            classes=self.classes,
            conf=self.conf,
            imgsz=self.imgsz,
            device=self.device,
            half=self.half,
            show=self.show,
            stream=True,
            verbose=False,
        )

        for _ in results:
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cv2.destroyAllWindows()
        print("[HumanDetector] Đã dừng.")