import aidcv as cv2
import numpy as np
from typing import List, Optional, Tuple
from ultralytics import YOLO
import time
from unidecode import unidecode
from src.models import Camera
from src.visualization import draw_overlay, draw_zones
from src.websocket_payload import build_detection_websocket_payload
from src.zone_geometry import assign_bboxes_to_zones
from src.zone_state_machine import ZoneStateMachine
from uart.uart_payload import build_occupied_zones_sync_payload, send_uart_payload
from uart.uart_manager import uart_manager
from utils import LOGGER, restore_level_names


MODEL_PATHS = {
    ("head", "nano", 1): "weights/head/yolo8n_rknn_model_b1",
    ("head", "nano", 2): "weights/head/yolo8n_rknn_model_b2",
    ("head", "nano", 4): "weights/head/yolo8n_rknn_model_b4",
    ("head", "nano", 8): "weights/head/yolo8n_rknn_model_b8",
    ("head", "medium", 1): "weights/head/yolo8m_rknn_model_b1",
    ("head", "medium", 2): "weights/head/yolo8m_rknn_model_b2",
    ("person", "nano", 1): "weights/person/yolov8n_rknn_model",
    ("person", "medium", 1): "weights/person/yolo11m_rknn_model",
}


class Detector:
    """
    Phát hiện người dùng YOLO, hỗ trợ 2 mode:
        - 'person'     : Phát hiện toàn thân người (dùng model COCO, filter class=0)
        - 'head'       : Phát hiện đầu người (dùng model head chuyên dụng)

    Source hỗ trợ:
        - int       : USB Camera (0, 1, 2, ...)
        - str RTSP  : "rtsp://user:pass@ip:port/stream"
        - str file  : "path/to/video.mp4" hoặc "path/to/image.jpg"
    """

    def __init__(
        self,
        source: str = "configs/rtsp.streams",
        mode: str = "head",
        model_size: str = "nano",
        conf: float = 0.50,
        show: bool = False,
        show_scale: float = 1.0,
        vid_stride: int = 1,
        batch_size: int = 1,
        cameras: Optional[List[Camera]] = None,
        zone_check_mode: str = "center",
        confirm_enter_time: float = 5.0,
        confirm_exit_time: float = 5.0,
        pending_enter_miss_grace_time: float = 1.5,
        verbose: bool = True,
    ):
        """
        Args:
            source         : int (USB cam), str (file/RTSP)
            mode           : Chế độ model ('head' hoặc 'person')
            model_size     : Kích thước model YOLO (nano, small, medium, large)
            conf           : Ngưỡng confidence (0.0 - 1.0)
            show           : Hiển thị cửa sổ kết quả
            show_scale     : Tỷ lệ hiển thị cửa sổ kết quả (mặc định 1.0)
            vid_stride     : Bước lặp khi xử lý video (mặc định 1)
            batch_size     : Số frame đưa vào một lần predict khi dùng batch mode
            cameras        : Danh sách camera và zones thuộc từng camera
            zone_check_mode: Cách xác định điểm đại diện khi kiểm tra zone:
                               - 'center': tâm bbox (mặc định)
                               - 'bottom_center': giữa cạnh dưới bbox
            confirm_enter_time: Thời gian xác nhận zone có người
            confirm_exit_time : Thời gian xác nhận zone không còn người
            pending_enter_miss_grace_time: Thời gian cho phép miss khi đang chờ enter
            verbose        : Hiển thị log chi tiết
        """

        self.source = source
        self.mode = mode
        self.model_size = model_size
        self.conf = conf
        self.show = show
        self.zone_check_mode = zone_check_mode
        self.show_scale = show_scale
        self.cameras = cameras or []
        self.all_zones = [zone for camera in self.cameras for zone in camera.zones]
        self.verbose = verbose
        self.vid_stride = vid_stride
        self.batch_size = int(batch_size)

        if self.batch_size < 1:
            raise ValueError("batch_size must be greater than or equal to 1.")

        if self.mode not in ("head", "person"):
            raise ValueError("mode must be 'head' or 'person'.")

        if len(self.cameras) != self.batch_size:
            raise ValueError(
                f"Number of cameras ({len(self.cameras)}) must match batch_size ({self.batch_size})."
            )

        # Log info
        LOGGER.info(f"Source: {self.source}")
        LOGGER.info(f"Mode: {self.mode}")
        LOGGER.info(f"Model size: {self.model_size}")
        LOGGER.info(f"Batch size: {self.batch_size}")
        LOGGER.info(f"Conf: {self.conf}")
        LOGGER.info(f"Show: {self.show}")
        LOGGER.info(f"Show scale: {self.show_scale}")
        LOGGER.info(f"Number of cameras: {len(self.cameras)}")
        LOGGER.info(f"Number of zones: {len(self.all_zones)}")
        LOGGER.info(f"Zone check mode: {self.zone_check_mode}")
        LOGGER.info(f"Video stride: {self.vid_stride}")
        LOGGER.info(f"Verbose: {self.verbose}")

        if not self.show:
            LOGGER.warning("Show is disabled, AI will run in background")     

        self.zone_state_machine = ZoneStateMachine(
            confirm_enter_time=confirm_enter_time,
            confirm_exit_time=confirm_exit_time,
            pending_enter_miss_grace_time=pending_enter_miss_grace_time,
        )

        # Load model
        self.model_path = self._resolve_model_path()
        self.model = self._load_model()

        self.is_running = True

        # Dữ liệu WebSocket mới nhất theo từng camera để gửi xuống Frontend
        self.latest_ws_payload = {
            "cameras": {},
        }

        # Dữ liệu UART mới nhất đã gửi đi
        self.latest_uart_payload = None

        # Khởi tạo UART Manager để gửi dữ liệu
        self.uart = uart_manager
    
    def _load_model(self):
        """Tải model YOLO dựa trên model_size và batch_size đã cấu hình."""
        return YOLO(self.model_path, task="detect")

    def _resolve_model_path(self) -> str:
        model_key = (self.mode, self.model_size, self.batch_size)
        model_path = MODEL_PATHS.get(model_key)
        if model_path is None:
            supported = ", ".join(
                f"{mode}/{size}/batch{batch}" for mode, size, batch in sorted(MODEL_PATHS)
            )
            raise ValueError(
                f"Unsupported mode/model_size/batch_size: "
                f"{self.mode}/{self.model_size}/batch{self.batch_size}. "
                f"Supported: {supported}"
            )
        return model_path

    def _inference(self):
        """
        Thực hiện nhận diện đối tượng trên luồng dữ liệu đầu vào.

        Returns:
            Iterable: Generator sinh ra đối tượng Result cho từng khung hình đơn lẻ.
            * Lưu ý: Dù cấu hình batch_size > 1 hay chạy đa luồng camera, kết quả 
              luôn được tự động trải phẳng (flatten) và trả về luân phiên 
              (VD: Cam1-Frame1 -> Cam2-Frame1 -> Cam1-Frame2 -> Cam2-Frame2...).
        """

        predict_kwargs = {
            "source": self.source,
            "conf": self.conf,
            "show": False,
            "stream": True,
            "verbose": False,
            "vid_stride": self.vid_stride,
            "batch": self.batch_size,
        }

        if self.mode == "person":
            predict_kwargs["classes"] = [0]

        results = self.model.predict(**predict_kwargs)

        return results

    @staticmethod
    def _parse_detections(boxes) -> Tuple[np.ndarray, np.ndarray]:
        """
        Trích xuất thông tin Bounding Box và Confidence từ đối tượng boxes của YOLO.
        
        Args:
            boxes: Đối tượng kết quả trả về từ YOLO chứa thông tin nhận diện.
            
        Returns:
            tuple: (bboxes, confs)
                - bboxes (np.ndarray): Mảng numpy chứa tọa độ bounding box (N, 4).
                - confs (np.ndarray): Mảng numpy chứa độ tin cậy của mỗi dự đoán (N,).
        """
        if boxes is not None and len(boxes) > 0:
            bboxes = boxes.xyxy.cpu().numpy()   # (N, 4)
            confs  = boxes.conf.cpu().numpy()   # (N,)

            valid_mask = np.isfinite(bboxes[:, :4]).all(axis=1) & np.isfinite(confs)
            invalid_count = int((~valid_mask).sum())
            if invalid_count:
                LOGGER.warning(
                    f"Bỏ qua {invalid_count} detection có bbox hoặc confidence không hợp lệ."
                )
                bboxes = bboxes[valid_mask]
                confs = confs[valid_mask]
        else:
            # Gán sẵn dtype float32 để đồng nhất với dữ liệu tensor của YOLO
            bboxes = np.empty((0, 4), dtype=np.float32)
            confs  = np.empty((0,),   dtype=np.float32)
            
        return bboxes, confs

    def _cleanup_run(self):
        """Dọn dẹp tài nguyên sau khi dừng vòng lặp run (RTSP stream, predictor, GUI)."""
        # 1. Đóng generator YOLO (giải phóng kết nối RTSP bên trong)
        if hasattr(self, '_results_gen') and self._results_gen is not None:
            try:
                self._results_gen.close()
                LOGGER.info("Đã đóng RTSP stream generator.")
            except Exception:
                pass
            self._results_gen = None

        # 2. Đóng LoadStreams dataset (chứa background threads đọc RTSP liên tục)
        #    Đây là nguyên nhân chính khiến CPU không được giải phóng sau khi dừng AI.
        if hasattr(self, 'model') and hasattr(self.model, 'predictor') and self.model.predictor is not None:
            predictor = self.model.predictor
            
            # Đóng dataset (LoadStreams) - dừng reader threads và release VideoCapture
            if hasattr(predictor, 'dataset') and predictor.dataset is not None:
                dataset = predictor.dataset
                try:
                    # LoadStreams có thuộc tính running để dừng threads
                    if hasattr(dataset, 'running'):
                        dataset.running = False
                    # Đợi các reader threads kết thúc
                    if hasattr(dataset, 'threads'):
                        for t in dataset.threads:
                            if t.is_alive():
                                t.join(timeout=3)
                    # Release các VideoCapture
                    if hasattr(dataset, 'caps'):
                        for cap in dataset.caps:
                            if cap and cap.isOpened():
                                cap.release()
                    # Gọi close() nếu có (ultralytics >= 8.1)
                    if hasattr(dataset, 'close'):
                        dataset.close()
                    LOGGER.info("Đã đóng RTSP reader threads và VideoCapture.")
                except Exception as e:
                    LOGGER.warning(f"Lỗi khi đóng dataset: {e}")
            
            # Xóa predictor để ultralytics tạo mới hoàn toàn khi gọi model.predict() lần sau
            try:
                self.model.predictor = None
                LOGGER.info("Đã xóa predictor (sẽ tạo mới khi start lại).")
            except Exception:
                pass

        # 3. Reset trạng thái các zone về EMPTY
        for zone in self.all_zones:
            zone.reset_zone()

        # 4. Đóng cửa sổ GUI
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

        # 5. Thu gom rác Python để giải phóng bộ nhớ
        import gc
        gc.collect()

    def stop(self):
        """Stop the detector"""
        self.is_running = False
        LOGGER.info("Đã nhận lệnh dừng AI")

    def update_detector_params(
        self,
        verbose: Optional[bool] = None,
        zone_check_mode: Optional[str] = None,
    ):
        """
        Update detector parameters.
        """
        if verbose is not None:
            self.verbose = verbose

        if zone_check_mode is not None:
            if zone_check_mode not in ("center", "bottom_center"):
                raise ValueError(
                    f"zone_check_mode must be 'center' or 'bottom_center', received: '{zone_check_mode}'"
                )
            self.zone_check_mode = zone_check_mode

        LOGGER.info("Detector params updated")

    def update_zone_state_machine_params(
        self,
        confirm_enter_time: Optional[float] = None,
        confirm_exit_time: Optional[float] = None,
        pending_enter_miss_grace_time: Optional[float] = None,
    ):
        """
        Hot-update ZoneStateMachine timing parameters without resetting zone states.
        """
        updates = {
            "confirm_enter_time": confirm_enter_time,
            "confirm_exit_time": confirm_exit_time,
            "pending_enter_miss_grace_time": pending_enter_miss_grace_time,
        }

        for param_name, param_value in updates.items():
            if param_value is None:
                continue

            next_value = float(param_value)
            if next_value < 0:
                raise ValueError(f"{param_name} must be greater than or equal to 0.")

            setattr(self.zone_state_machine, param_name, next_value)

        LOGGER.info(
            "ZoneStateMachine params updated: "
            f"confirm_enter_time={self.zone_state_machine.confirm_enter_time}, "
            f"confirm_exit_time={self.zone_state_machine.confirm_exit_time}, "
            f"pending_enter_miss_grace_time={self.zone_state_machine.pending_enter_miss_grace_time}"
        )

    def sync_uart(self):
        """Gửi dữ liệu các zone đang có người khi nhận được lệnh sync (lọc bỏ zone robot đang đứng)."""
        latest_received_data = self.uart.latest_received_data if hasattr(self, "uart") else None
        sync_payload = build_occupied_zones_sync_payload(self.all_zones, latest_received_data)

        if sync_payload["detected"]:
            send_uart_payload(self.uart, sync_payload, is_sync=True)
            LOGGER.info(f"Đã gửi dữ liệu {len(sync_payload['detected'])} zone có người theo lệnh sync.")
        else:
            send_uart_payload(self.uart, sync_payload, is_sync=True)
            LOGGER.info("Không có zone nào đang có người (hoặc đã bị lược bỏ do robot đang đứng đó), gửi xác nhận sync rỗng.")

    def run(self):
        """
        Khởi chạy vòng lặp nhận diện và giám sát đối tượng theo thời gian thực.
        """
        window_names = {
            camera.id: f"HumanDetector - {camera.name} ({camera.id})"
            for camera in self.cameras
        }
        if self.show:
            for win_name in window_names.values():
                cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)

        # Lưu reference generator để có thể đóng (close) khi stop
        self._results_gen = self._inference()
        prev_times_by_camera = {}

        # Restore logger level names
        _restored = False

        try:
            for result_index, result in enumerate(self._results_gen):
                if not self.is_running:
                    LOGGER.info("Dừng vòng lặp nhận diện.")
                    break
                
                if not _restored:
                    restore_level_names()
                    _restored = True

                if not self.cameras:
                    LOGGER.warning("Không có camera nào được cấu hình.")
                    break

                camera = self.cameras[result_index % len(self.cameras)]
                zones = camera.zones

                # Lấy độ phân giải camera
                if camera.resolution is None:
                    h, w = result.orig_img.shape[:2]
                    camera.resolution = (w, h)
                
                resolution = camera.resolution

                # 1. Trích xuất thông tin Bounding Box
                bboxes, confs = self._parse_detections(result.boxes)

                # 2. Gắn bbox vào các vùng zones
                zone_names, zone_counts = assign_bboxes_to_zones(
                    bboxes,
                    zones,
                    self.zone_check_mode,
                )
                
                # 3. State Machine: Cập nhật trạng thái từng vùng
                uart_payload = self.zone_state_machine.update(
                    zones,
                    zone_counts,
                )

                # 4. Gửi dữ liệu qua UART
                if uart_payload["detected"] or uart_payload["cleared"]:
                    self.latest_uart_payload = uart_payload
                    try:
                        send_uart_payload(self.uart, uart_payload)
                    except Exception as e:
                        LOGGER.error(f"Lỗi khi gửi dữ liệu qua UART: {e}")

                # 5. Đẩy dữ liệu WebSocket cho web preview
                camera_ws_payload = build_detection_websocket_payload(
                    camera,
                    resolution,
                    bboxes,
                    confs,
                    zones,
                    zone_counts,
                )
                self.latest_ws_payload["cameras"][camera.id] = camera_ws_payload

                # Tính FPS
                current_time = time.time()
                prev_time = prev_times_by_camera.get(camera.id)
                fps = 0.0 if prev_time is None else 1.0 / max(current_time - prev_time, 1e-6)
                prev_times_by_camera[camera.id] = current_time

                # Verbose log
                if self.verbose:
                    LOGGER.info(f"Camera: {camera.name}, Object: {len(bboxes)}, FPS: {fps:.1f}")

                if self.show:
                    win_name = window_names.get(camera.id, f"HumanDetector - {camera.id}")

                    # Copy frame gốc
                    frame = result.orig_img.copy()

                    # Vẽ các vùng giám sát
                    frame = draw_zones(frame, zones)

                    # Vẽ các đối tượng được phát hiện
                    frame = draw_overlay(frame, bboxes, confs, zone_names)

                    # Vẽ FPS lên góc trên bên trái
                    cv2.putText(frame, f"{unidecode(camera.name)} FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)

                    if self.show_scale != 1.0:
                        h, w = frame.shape[:2]
                        new_dim = (int(w * self.show_scale), int(h * self.show_scale))
                        resized_frame = cv2.resize(frame, new_dim)

                        padded_frame = cv2.copyMakeBorder(
                            resized_frame,
                            20, 20, 20, 20,
                            cv2.BORDER_CONSTANT,
                            value=(255, 255, 255)  # trắng
                        )

                        cv2.imshow(win_name, padded_frame)
                    else:
                        cv2.imshow(win_name, frame)
                else:
                    pass

        except Exception as e:
            LOGGER.error(f"Lỗi xảy ra trong vòng lặp run: {e}", exc_info=True)

        finally:
            # Dọn dẹp tài nguyên: đóng RTSP stream, reset zone, đóng GUI
            self._cleanup_run()
            LOGGER.info("HumanDetector Đã dừng.")
# refresh
