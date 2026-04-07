import os
import aidcv as cv2
import numpy as np
from typing import List, Optional, Set
from ultralytics import YOLO
from utils import LOGGER


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
        "person":     "models/person/yolo26n_rknn_model",
        "human_head": "models/head/yolov8_nano_rknn_model",
    }

    # Màu sắc cho từng ROI (BGR) — xanh lá khi rỗng, đỏ khi có người
    COLOR_ROI_EMPTY   = (0, 200, 0)    # xanh lá
    COLOR_ROI_ACTIVE  = (0, 0, 220)    # đỏ
    COLOR_BBOX_NORMAL = (255, 0, 0)    # xanh dương — bbox ngoài ROI
    COLOR_BBOX_IN_ROI = (0, 0, 220)    # đỏ   — bbox trong ROI

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
        roi_check_mode: str = "center",
        monitored_areas: List[dict] = None,
    ):
        """
        Args:
            mode           : 'person' hoặc 'human_head'
            model_path     : Đường dẫn model .pt (None = dùng mặc định theo mode)
            source         : int (USB cam), str (file/RTSP)
            conf           : Ngưỡng confidence (0.0 - 1.0)
            imgsz          : Kích thước ảnh đầu vào
            device         : GPU index (0, 1, ...) hoặc 'cpu'
            half           : Dùng FP16 để tăng tốc (chỉ hoạt động với GPU)
            show           : Hiển thị cửa sổ kết quả
            roi_check_mode : Cách xác định điểm đại diện khi kiểm tra ROI:
                               'center'        — tâm bbox (mặc định)
                               'bottom_center' — giữa cạnh dưới bbox
        """
        if mode not in self.DEFAULT_MODELS:
            raise ValueError(f"mode phải là 'person' hoặc 'human_head', nhận được: '{mode}'")
        if roi_check_mode not in ("center", "bottom_center"):
            raise ValueError(f"roi_check_mode phải là 'center' hoặc 'bottom_center'")

        self.mode = mode
        self.source = source
        self.conf = conf
        self.imgsz = imgsz
        self.device = device
        self.half = half
        self.show = show
        self.roi_check_mode = roi_check_mode

        # Log info
        LOGGER.info(f"Source: {source}")
        LOGGER.info(f"Mode: {mode}")
        LOGGER.info(f"Conf: {conf}")
        LOGGER.info(f"Imgsz: {imgsz}")
        LOGGER.info(f"Device: {device}")
        LOGGER.info(f"Half: {half}")
        LOGGER.info(f"Show: {show}")
        LOGGER.info(f"ROI Check Mode: {roi_check_mode}")        

        # Initialize monitored areas
        if monitored_areas is None:
            raise ValueError("monitored_areas must not be None")
        else:
            self.monitored_areas = monitored_areas
            # Convert pts to numpy arrays if they are lists (from JSON)
            for area in self.monitored_areas:
                if not isinstance(area["pts"], np.ndarray):
                    area["pts"] = np.array(area["pts"], dtype=np.int32)

        # Mode 'person' dùng model COCO nên cần filter class 0 (person)
        # Mode 'human_head' dùng model chuyên biệt, không cần filter
        self.classes = [0] if mode == "person" else None

        # Load model
        resolved_path = model_path or self.DEFAULT_MODELS[mode]
        self.model = YOLO(
            resolved_path, 
            task="detect"
        )

    def _draw_monitored_areas(
        self,
        frame: np.ndarray,
        active_area_names: set = None,
    ) -> np.ndarray:
        """
        Vẽ các vùng giám sát lên frame.

        Args:
            frame             : Frame gốc (BGR).
            active_area_names : Tập tên các ROI hiện đang có bbox bên trong.
                                ROI này sẽ được highlight đỏ thay vì xanh.
        """
        if active_area_names is None:
            active_area_names = set()

        overlay = frame.copy()
        for area in self.monitored_areas:
            pts  = area["pts"]
            name = area["name"]
            is_active = name in active_area_names

            color = self.COLOR_ROI_ACTIVE if is_active else self.COLOR_ROI_EMPTY

            # Tô màu nền bán trong suốt
            cv2.fillPoly(overlay, [pts], color=color)

            # Vẽ viền vùng
            cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)

            # Vẽ nhãn tên vùng tại điểm trung tâm
            cx = int(pts[:, 0].mean())
            cy = int(pts[:, 1].mean())
            cv2.putText(frame, name, (cx, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        # Blend overlay (alpha=0.2)
        cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
        return frame

    def _draw_detections(
        self,
        frame: np.ndarray,
        bboxes: np.ndarray,
        confs: np.ndarray,
        bbox_roi_names: List[Optional[str]],
    ) -> np.ndarray:
        """
        Vẽ bounding boxes thủ công lên frame.

        Args:
            frame          : Frame BGR.
            bboxes         : Array (N, 4) tọa độ (x1,y1,x2,y2).
            confs          : Array (N,) giá trị confidence.
            bbox_roi_names : List độ dài N — tên ROI mà bbox đó thuộc về
                             (None nếu bbox không nằm trong ROI nào).
        """
        for bbox, conf, roi_name in zip(bboxes, confs, bbox_roi_names):
            x1, y1, x2, y2 = map(int, bbox[:4])
            in_roi = roi_name is not None
            color  = self.COLOR_BBOX_IN_ROI if in_roi else self.COLOR_BBOX_NORMAL

            # Vẽ bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness=2)

            # Tạo label: luôn hiện conf, thêm tên ROI nếu trong vùng
            label = f"{conf:.2f}"
            if in_roi:
                label = f"{roi_name} | {conf:.2f}"

            # Nền nhãn
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
            cv2.putText(
                frame, label,
                (x1 + 2, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (255, 255, 255), 1, cv2.LINE_AA,
            )

        return frame

    def is_bbox_in_roi(
        self,
        bbox: tuple,
        roi_pts: np.ndarray,
        mode: str = "center",
    ) -> bool:
        """
        Kiểm tra xem một bounding box có nằm trong vùng ROI (đa giác) hay không.

        Args:
            bbox    : Bounding box dạng (x1, y1, x2, y2) — tọa độ pixel.
            roi_pts : Mảng các điểm đa giác ROI, shape (N, 2), dtype int32.
                      Thường là area["pts"] trong monitored_areas.
            mode    : Phương thức kiểm tra điểm đại diện của bbox:
                        - 'center'        : Điểm trung tâm (cx, cy) của bbox.
                        - 'bottom_center' : Điểm giữa-dưới (cx, y2) của bbox
                                           (phù hợp cho người đứng, vì chân
                                            chạm đất = điểm thực tế nhất).

        Returns:
            True nếu điểm đại diện nằm trong (hoặc trên cạnh) đa giác ROI,
            False nếu nằm ngoài.

        Raises:
            ValueError: Nếu mode không hợp lệ.

        Example:
            >>> boxes = result.boxes.xyxy.cpu().numpy()  # shape (N, 4)
            >>> for bbox in boxes:
            ...     in_roi = detector.is_bbox_in_roi(bbox, area["pts"], mode="bottom_center")
        """
        if mode not in ("center", "bottom_center"):
            raise ValueError(
                f"mode phải là 'center' hoặc 'bottom_center', nhận được: '{mode}'"
            )

        x1, y1, x2, y2 = bbox[:4]

        if mode == "center":
            # Điểm trung tâm của bounding box
            point = (int((x1 + x2) / 2), int((y1 + y2) / 2))
        else:  # bottom_center
            # Điểm giữa cạnh dưới bbox — thường gần mặt đất nhất
            point = (int((x1 + x2) / 2), int(y2))

        # cv2.pointPolygonTest trả về:
        #   > 0  : điểm nằm trong đa giác
        #   = 0  : điểm nằm trên cạnh đa giác
        #   < 0  : điểm nằm ngoài đa giác
        result = cv2.pointPolygonTest(roi_pts, point, measureDist=False)
        return result >= 0

    def run(self):
        """
        Chạy detection liên tục trên source đã cấu hình.
        - Kiểm tra từng bbox có nằm trong ROI nào không.
        - Bbox trong ROI: highlight đỏ + gắn nhãn tên ROI.
        - ROI đang có người: viền + nền đỏ thay vì xanh.
        Nhấn 'q' để dừng.
        """

        win_name = f"HumanDetector [{self.mode}]"
        if self.show:
            cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)

        results = self.model.predict(
            source=self.source,
            classes=self.classes,
            conf=self.conf,
            imgsz=self.imgsz,
            device=self.device,
            half=self.half,
            show=False,
            stream=True,
            verbose=False,
        )

        try:
            for result in results:
                # Lấy frame gốc (chưa vẽ gì)
                frame = result.orig_img.copy()

                # Lấy danh sách bbox và confidence
                boxes = result.boxes
                if boxes is not None and len(boxes) > 0:
                    bboxes = boxes.xyxy.cpu().numpy()   # (N, 4)
                    confs  = boxes.conf.cpu().numpy()   # (N,)
                else:
                    bboxes = np.empty((0, 4), dtype=np.float32)
                    confs  = np.empty((0,),   dtype=np.float32)

                # ── Kiểm tra từng bbox thuộc ROI nào ──────────────────────────
                # Mỗi phần tử là tên ROI chứa bbox đó (None = không thuộc ROI nào).
                # Nếu 1 bbox nằm trong nhiều ROI, ưu tiên ROI đầu tiên tìm được.
                # Nếu 2+ head cùng nằm trong 1 ROI → đều được xử lý bình thường.
                bbox_roi_names: List[Optional[str]] = [None] * len(bboxes)
                active_area_names: Set[str] = set()

                if len(bboxes) > 0:
                    for area in self.monitored_areas:
                        for i, bbox in enumerate(bboxes):
                            if self.is_bbox_in_roi(bbox, area["pts"], mode=self.roi_check_mode):
                                if bbox_roi_names[i] is None:
                                    bbox_roi_names[i] = area["name"]
                                active_area_names.add(area["name"])

                # ── Vẽ ROI (highlight đỏ nếu có người) ───────────────────────
                frame = self._draw_monitored_areas(frame, active_area_names)

                # ── Vẽ bbox (highlight đỏ + nhãn ROI nếu trong vùng) ─────────
                frame = self._draw_detections(frame, bboxes, confs, bbox_roi_names)

                if self.show:
                    cv2.imshow(win_name, frame)

        finally:
            cv2.destroyAllWindows()
            LOGGER.info("HumanDetector Đã dừng.")
            # Force-exit để tránh crash C++ runtime khi cleanup
            # RTSP stream hoặc GPU context (ultralytics/OpenCV known issue)
            os._exit(0)