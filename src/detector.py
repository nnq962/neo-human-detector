import aidcv as cv2
import numpy as np
from typing import List, Optional
from ultralytics import YOLO
import time
from src.models import Zone
from src.visualization import draw_overlay, draw_zones
from src.websocket_payload import build_detection_websocket_payload
from src.zone_geometry import assign_bboxes_to_zones
from src.zone_state_machine import ZoneStateMachine
from uart.uart_payload import build_occupied_zones_sync_payload, send_uart_payload
from uart.uart_manager import uart_manager
from utils import LOGGER, restore_level_names

class Detector:
    """
    Phát hiện người dùng YOLO, hỗ trợ 2 mode:
        - 'person'     : Phát hiện toàn thân người (dùng model COCO, filter class=0)
        - 'human_head' : Phát hiện đầu người (dùng model head chuyên dụng)

    Source hỗ trợ:
        - int       : USB Camera (0, 1, 2, ...)
        - str RTSP  : "rtsp://user:pass@ip:port/stream"
        - str file  : "path/to/video.mp4" hoặc "path/to/image.jpg"
    """

    def __init__(
        self,
        source=0,
        model_path: str = "weights/head/yolov8_nano_rknn_model",
        conf: float = 0.50,
        show: bool = False,
        show_scale: float = 1.0,
        vid_stride: int = 1,
        zones: Optional[List[Zone]] = None,
        zone_check_mode: str = "center",
        confirm_enter_time: float = 5.0,
        confirm_exit_time: float = 5.0,
        pending_enter_miss_grace_time: float = 1.5,
        verbose: bool = True,
    ):
        """
        Args:
            source         : int (USB cam), str (file/RTSP)
            model_path     : Path to the YOLO RKNN model
            conf           : Ngưỡng confidence (0.0 - 1.0)
            show           : Hiển thị cửa sổ kết quả
            show_scale     : Tỷ lệ hiển thị cửa sổ kết quả (mặc định 1.0)
            vid_stride     : Bước lặp khi xử lý video (mặc định 1)
            zones          : Danh sách các Zone được giám sát
            zone_check_mode: Cách xác định điểm đại diện khi kiểm tra zone:
                               - 'center': tâm bbox (mặc định)
                               - 'bottom_center': giữa cạnh dưới bbox
            confirm_enter_time: Thời gian xác nhận zone có người
            confirm_exit_time : Thời gian xác nhận zone không còn người
            pending_enter_miss_grace_time: Thời gian cho phép miss khi đang chờ enter
            verbose        : Hiển thị log chi tiết
        """

        self.source = source
        self.model_path = model_path
        self.conf = conf
        self.show = show
        self.zone_check_mode = zone_check_mode
        self.show_scale = show_scale
        self.zones = zones or []
        self.verbose = verbose
        self.vid_stride = vid_stride

        # Log info
        LOGGER.info(f"Source: {self.source}")
        LOGGER.info(f"Model path: {self.model_path}")
        LOGGER.info(f"Conf: {self.conf}")
        LOGGER.info(f"Show: {self.show}")
        LOGGER.info(f"Show scale: {self.show_scale}")
        LOGGER.info(f"Number of zones: {len(self.zones)}")
        LOGGER.info(f"Zone check mode: {self.zone_check_mode}")
        LOGGER.info(f"Video stride: {self.vid_stride}")
        LOGGER.info(f"Verbose: {self.verbose}")

        if not self.show:
            LOGGER.warning("Show is disabled, AI will run in background")     

        # Dữ liệu WebSocket mới nhất để gửi xuống Frontend
        self.latest_ws_payload = None

        # Dữ liệu UART mới nhất đã gửi đi
        self.latest_uart_payload = None

        self.zone_state_machine = ZoneStateMachine(
            confirm_enter_time=confirm_enter_time,
            confirm_exit_time=confirm_exit_time,
            pending_enter_miss_grace_time=pending_enter_miss_grace_time,
        )

        # Load model
        self.model = YOLO(
            self.model_path, 
            task="detect"
        )

        self.is_running = True

        # Khởi tạo UART Manager để gửi dữ liệu
        self.uart = uart_manager

    def _inference(self):
        """
        Thực hiện nhận diện đối tượng trên luồng dữ liệu đầu vào.

        Project hiện chỉ dùng bbox + zone occupancy.

        Returns:
            Iterable: Trình tạo (generator) trả về kết quả nhận diện cho từng khung hình.
        """

        results = self.model.predict(
            source=self.source,
            conf=self.conf,
            show=False,
            stream=True,
            verbose=False,
            vid_stride=self.vid_stride,
        )

        return results

    def _parse_detections(self, boxes):
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
        else:
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
        for zone in self.zones:
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

    def update_detector_params(self, verbose: bool):
        """
        Update detector parameters.
        """
        self.verbose = verbose
        LOGGER.info("Detector params updated")

    def update_zone(self, zones: Optional[List[Zone]]):
        """
        Update the detection zone.
        """
        self.zones = zones or []
        LOGGER.info("Detector zones updated")

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
        sync_payload = build_occupied_zones_sync_payload(self.zones, latest_received_data)

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
        win_name = f"HumanDetector"
        if self.show:
            cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)

        # Lưu reference generator để có thể đóng (close) khi stop
        self._results_gen = self._inference()
        prev_time = time.time()
        # Restore logger level names
        _restored = False

        try:
            for result in self._results_gen:
                if not self.is_running:
                    LOGGER.info("Dừng vòng lặp nhận diện.")
                    break
                
                if not _restored:
                    restore_level_names()
                    _restored = True
                
                frame = result.orig_img.copy()

                # 1. Trích xuất thông tin Bounding Box
                bboxes, confs = self._parse_detections(result.boxes)

                # 2. Gắn bbox vào các vùng zones
                zone_names, zone_has_detection = assign_bboxes_to_zones(
                    bboxes,
                    self.zones,
                    self.zone_check_mode,
                )
                
                # 3. State Machine: Cập nhật trạng thái từng vùng
                current_time = time.time()
                uart_payload = self.zone_state_machine.update(
                    self.zones,
                    zone_has_detection,
                    current_time,
                )

                # 4. Đẩy dữ liệu WebSocket cho web preview
                self.latest_ws_payload = build_detection_websocket_payload(
                    frame,
                    bboxes,
                    confs,
                    self.zones,
                )

                # 5. Gửi dữ liệu qua UART
                if uart_payload["detected"] or uart_payload["cleared"]:
                    self.latest_uart_payload = uart_payload
                    send_uart_payload(self.uart, uart_payload)

                # Tính FPS
                current_time = time.time()
                fps = 1.0 / (current_time - prev_time)
                prev_time = current_time

                # Verbose log
                if self.verbose:
                    LOGGER.info(f"FPS: {fps:.1f}")

                if self.show:
                    # Vẽ các vùng giám sát
                    frame = draw_zones(frame, self.zones)

                    # Vẽ các đối tượng được phát hiện
                    frame = draw_overlay(frame, bboxes, confs, zone_names)

                    # Vẽ FPS lên góc trên bên trái
                    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)

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
