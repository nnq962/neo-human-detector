import os
import aidcv as cv2
import numpy as np
from typing import List, Optional, Set
from ultralytics import YOLO
from utils import LOGGER
import time


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

    DEFAULT_MODELS = "models/head/yolov8_nano_rknn_model"

    # Màu sắc cho từng ROI (BGR)
    COLOR_ROI_EMPTY   = (0, 200, 0)    # xanh lá
    COLOR_ROI_ACTIVE  = (0, 0, 220)    # đỏ
    COLOR_BBOX_NORMAL = (255, 0, 0)    # xanh dương — bbox ngoài ROI
    COLOR_BBOX_IN_ROI = (0, 0, 220)    # đỏ   — bbox trong ROI

    def __init__(
        self,
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

        if roi_check_mode not in ("center", "bottom_center"):
            raise ValueError(f"roi_check_mode phải là 'center' hoặc 'bottom_center'")

        self.source = source
        self.conf = conf
        self.imgsz = imgsz
        self.device = device
        self.half = half
        self.show = show
        self.roi_check_mode = roi_check_mode

        # Log info
        LOGGER.info(f"Source: {source}")
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

        # Khởi tạo bộ chấm điểm ROI
        self.roi_scores = {area["name"]: 0.0 for area in self.monitored_areas}
        self.roi_state = {area["name"]: False for area in self.monitored_areas}  # Trạng thái ổn định

        self.SCORE_REWARD = 1.0
        self.SCORE_PENALTY = 2.0
        self.SCORE_MAX = 100.0
        self.CONFIRM_THRESHOLD = 50.0
        self.RELEASE_THRESHOLD = 20.0

        # Load model
        self.model = YOLO(
            self.DEFAULT_MODELS, 
            task="detect"
        )

    def _draw_monitored_areas(
        self,
        frame: np.ndarray,
        active_area_names: set = None,
    ) -> np.ndarray:
        """
        Vẽ lớp phủ các vùng giám sát (ROI) lên khung hình.
        Highlight các vùng trong `active_area_names` bằng màu cảnh báo, các vùng còn lại dùng màu mặc định.

        Args:
            frame (np.ndarray): Khung hình ảnh gốc (hệ màu BGR).
            active_area_names (set, optional): Tập hợp tên các ROI đang ở trạng thái kích hoạt.
                Nếu None, tất cả các vùng sẽ được vẽ ở trạng thái mặc định.

        Returns:
            np.ndarray: Khung hình đã được chèn các hiệu ứng hình ảnh của ROI.
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

            # Nhãn tên vùng kèm điểm số
            score = self.roi_scores.get(name, 0.0)
            label = f"{name} [{score:.1f}]"

            # Vẽ nhãn tại điểm trung tâm
            cx = int(pts[:, 0].mean())
            cy = int(pts[:, 1].mean())
            cv2.putText(frame, label, (cx, cy),
                        cv2.FONT_HERSHEY_DUPLEX, 0.8, color, 2)

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
        Vẽ khung nhận diện (Bounding Box) và thông tin đối tượng lên khung hình.
        Hiển thị ID, độ tin cậy và điểm số tín nhiệm nếu đối tượng thuộc vùng giám sát.

        Args:
            frame (np.ndarray): Khung hình ảnh gốc (BGR).
            bboxes (np.ndarray): Mảng tọa độ các khung nhận diện (N, 4).
            confs (np.ndarray): Mảng giá trị độ tin cậy (N,).
            bbox_roi_names (List[Optional[str]]): Danh sách tên ROI tương ứng của mỗi đối tượng.

        Returns:
            np.ndarray: Khung hình đã được vẽ thông tin nhận diện.
        """

        for bbox, conf, roi_name in zip(bboxes, confs, bbox_roi_names):
            x1, y1, x2, y2 = map(int, bbox[:4])
            in_roi = roi_name is not None
            color  = self.COLOR_BBOX_IN_ROI if in_roi else self.COLOR_BBOX_NORMAL

            # Vẽ bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness=2)

            # Tạo label: luôn hiện conf, thêm tên ROI nếu trong vùng
            if in_roi:
                # Nếu nằm trong ROI, lấy điểm số ra (làm tròn 1 chữ số thập phân)
                label = f"[{roi_name}] [{conf:.2f}]"
            else:
                # Nếu chạy rông bên ngoài, chỉ hiện ID và Conf
                label = f"[{conf:.2f}]"

            # Nền nhãn
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_DUPLEX, 0.55, 1)
            cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)

            # Viết chữ
            cv2.putText(
                frame, label,
                (x1 + 2, y1 - 4),
                cv2.FONT_HERSHEY_DUPLEX, 0.55,
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
        Kiểm tra một bounding box có nằm trong vùng đa giác (ROI) hay không.

        Args:
            bbox (tuple/np.ndarray): Tọa độ khung nhận diện (x1, y1, x2, y2).
            roi_pts (np.ndarray): Mảng các đỉnh của đa giác ROI (N, 2).
            mode (str): Chế độ kiểm tra: 
                - 'center': Dựa trên điểm tâm khung.
                - 'bottom_center': Dựa trên điểm giữa cạnh dưới.

        Returns:
            bool: True nếu điểm đại diện nằm trong hoặc trên cạnh ROI.

        Raises:
            ValueError: Nếu `mode` không hợp lệ.
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
            # Điểm giữa cạnh dưới bbox
            point = (int((x1 + x2) / 2), int(y2))

        # cv2.pointPolygonTest trả về:
        #   > 0  : điểm nằm trong đa giác
        #   = 0  : điểm nằm trên cạnh đa giác
        #   < 0  : điểm nằm ngoài đa giác
        result = cv2.pointPolygonTest(roi_pts, point, measureDist=False)
        return result >= 0

    def inference(self):
        """
        Thực hiện nhận diện và theo dõi đối tượng trên luồng dữ liệu đầu vào.

        Phương thức này cấu hình và chạy mô hình YOLO với bộ theo dõi ByteTrack 
        để phát hiện và duy trì định danh (ID) cho các đối tượng.

        Returns:
            Iterable: Trình tạo (generator) trả về kết quả nhận diện cho từng khung hình.
        """

        results = self.model.predict(
            source=self.source,
            conf=self.conf,
            imgsz=self.imgsz,
            device=self.device,
            half=self.half,
            show=False,
            stream=True,
            verbose=False,
        )

        return results

    def run(self):
        """
        Khởi chạy vòng lặp nhận diện và giám sát đối tượng theo thời gian thực.

        Quy trình xử lý bao gồm:
        1. Nhận dữ liệu từ mô hình tracking.
        2. Kiểm tra sự hiện diện của đối tượng trong các vùng ROI.
        3. Áp dụng logic điểm số tín nhiệm để xác thực trạng thái vùng.
        4. Hiển thị hình ảnh trực quan và xử lý phím bấm (nhấn 'q' để dừng).
        """

        win_name = f"HumanDetector"
        if self.show:
            cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)

        results = self.inference()
        prev_time = time.time()

        try:
            for result in results:
                speed_dict = result.speed
                inference_time = speed_dict['inference']
                # LOGGER.info(f"Inference time: {inference_time:.1f}ms")
                
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

                # ── KIỂM TRA ĐỐI TƯỢNG TRONG ROI VÀ TÍNH ĐIỂM ───────────────
                bbox_roi_names: List[Optional[str]] = [None] * len(bboxes)
                detected_rois: Set[str] = set()

                if len(bboxes) > 0:
                    for i, bbox in enumerate(bboxes):
                        for area in self.monitored_areas:
                            if self.is_bbox_in_roi(bbox, area["pts"], mode=self.roi_check_mode):
                                bbox_roi_names[i] = area["name"]
                                detected_rois.add(area["name"])
                                break  # Ngừng kiểm tra các vùng khác nếu đã thuộc 1 vùng

                active_area_names: Set[str] = set()

                for area in self.monitored_areas:
                    roi_name = area["name"]
                    head_detected_in_roi = roi_name in detected_rois

                    # Cập nhật điểm số
                    if head_detected_in_roi:
                        self.roi_scores[roi_name] = min(
                            self.SCORE_MAX, 
                            self.roi_scores[roi_name] + self.SCORE_REWARD
                        )
                    else:
                        self.roi_scores[roi_name] = max(
                            0.0, 
                            self.roi_scores[roi_name] - self.SCORE_PENALTY
                        )

                    score = self.roi_scores[roi_name]

                    # Hysteresis logic
                    if not self.roi_state[roi_name] and score >= self.CONFIRM_THRESHOLD:
                        self.roi_state[roi_name] = True
                    elif self.roi_state[roi_name] and score <= self.RELEASE_THRESHOLD:
                        self.roi_state[roi_name] = False

                    # Nếu vùng đang active, thêm vào tập để vẽ đỏ
                    if self.roi_state[roi_name]:
                        active_area_names.add(roi_name)

                # Vẽ lên frame
                frame = self._draw_monitored_areas(
                    frame, 
                    active_area_names
                )
                frame = self._draw_detections(
                    frame, 
                    bboxes, 
                    confs, 
                    bbox_roi_names
                )

                # Tính FPS
                current_time = time.time()
                fps = 1.0 / (current_time - prev_time)
                prev_time = current_time

                # Hiển thị FPS
                cv2.putText(frame, f"FPS: {fps:.1f}", (20, 50), 
                            cv2.FONT_HERSHEY_DUPLEX, 1, (0, 255, 0), 2)

                if self.show:
                    cv2.imshow(win_name, frame)

        finally:
            cv2.destroyAllWindows()
            LOGGER.info("HumanDetector Đã dừng.")
            # Force-exit để tránh crash C++ runtime khi cleanup
            # RTSP stream hoặc GPU context (ultralytics/OpenCV known issue)
            os._exit(0)