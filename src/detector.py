import aidcv as cv2
import numpy as np
from typing import List, Optional
from ultralytics import YOLO
import time
import threading
import queue
from src.models import Zone, ZoneState, TrackedPerson
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

    COLOR_BBOX_NORMAL = (255, 0, 0)    # xanh dương — bbox ngoài zone
    COLOR_BBOX_IN_ZONE = (0, 200, 0)    # xanh lá   — bbox trong zone

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
            zone_check_mode : Cách xác định điểm đại diện khi kiểm tra zone:
                               'center'        — tâm bbox (mặc định)
                               'bottom_center' — giữa cạnh dưới bbox
            verbose        : Hiển thị log chi tiết
        """

        if zone_check_mode not in ("center", "bottom_center"):
            raise ValueError(f"zone_check_mode phải là 'center' hoặc 'bottom_center'")

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

        # Global ID Tracker
        self.global_tracked_ids = {}

        # Time Thresholds -------------------------------------------------------------------------------------
        self.CONFIRM_ENTER_TIME = 10.0      # Ngồi liên tục > 10s mới tính là OCCUPIED
        self.CONFIRM_EXIT_TIME = 8.0        # Mất dấu > 8s mới tính là EMPTY
        self.ID_GARBAGE_COLLECT_TIME = 5.0  # Quá 5s không thấy ID trên toàn camera -> Dọn rác
        # -----------------------------------------------------------------------------------------------------

        # Load model
        self.model = YOLO(
            self.model_path, 
            task="detect"
        )

        self.is_running = True

        # Khởi tạo UART Manager để gửi dữ liệu
        self.uart = uart_manager

    def _draw_zones(
        self,
        frame: np.ndarray,
    ) -> np.ndarray:
        """
        Vẽ lớp phủ các vùng lên khung hình.
        Sử dụng màu sắc tương ứng với trạng thái của từng vùng dựa trên ZoneColor.

        Args:
            frame (np.ndarray): Khung hình ảnh gốc (hệ màu BGR).

        Returns:
            np.ndarray: Khung hình đã được chèn các hiệu ứng hình ảnh của zone.
        """

        overlay = frame.copy()
        for zone in self.zones:
            pts  = zone.pts
            name = zone.name
            color = zone.get_current_color()

            # Tô màu nền bán trong suốt
            cv2.fillPoly(overlay, [pts], color=color)

            # Vẽ viền vùng
            cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)

            # Nhãn tên vùng kèm trạng thái
            label = f"{name} [{zone.state.value}]"

            # Vẽ nhãn tại điểm trung tâm
            cx = int(pts[:, 0].mean())
            cy = int(pts[:, 1].mean())
            cv2.putText(frame, label, (cx, cy),
                        cv2.FONT_HERSHEY_DUPLEX, 0.8, color, 2)

        # Blend overlay (alpha=0.2)
        cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
        return frame

    def _draw_overlay(
        self,
        frame: np.ndarray,
        bboxes: np.ndarray,
        confs: np.ndarray,
        ids: np.ndarray,
        zone_names: List[Optional[str]],
    ) -> np.ndarray:
        """
        Vẽ khung nhận diện (Bounding Box) và thông tin đối tượng lên khung hình.
        Hiển thị ID, độ tin cậy và điểm số tín nhiệm nếu đối tượng thuộc vùng giám sát.

        Args:
            frame (np.ndarray): Khung hình ảnh gốc (BGR).
            bboxes (np.ndarray): Mảng tọa độ các khung nhận diện (N, 4).
            confs (np.ndarray): Mảng giá trị độ tin cậy (N,).
            ids (np.ndarray): Mảng ID của các đối tượng (N,).
            zone_names (List[Optional[str]]): Danh sách tên zone tương ứng của mỗi đối tượng.

        Returns:
            np.ndarray: Khung hình đã được vẽ thông tin nhận diện.
        """

        for bbox, conf, obj_id, zone_name in zip(bboxes, confs, ids, zone_names):
            x1, y1, x2, y2 = map(int, bbox[:4])
            in_zone = zone_name is not None
            color  = self.COLOR_BBOX_IN_ZONE if in_zone else self.COLOR_BBOX_NORMAL

            # Vẽ bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness=2)

            # Tạo label: luôn hiện id, conf, thêm tên zone nếu trong vùng
            id_text = f"ID {obj_id}" if obj_id != -1 else "ID:?"
            if in_zone:
                # Nếu nằm trong zone, hiện tên zone
                label = f"[{id_text}] [{conf:.2f}] [{zone_name}]"
            else:
                # Nếu chạy rông bên ngoài, chỉ hiện ID và Conf
                label = f"[{id_text}] [{conf:.2f}]"

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

    def _is_bbox_in_zone(
        self,
        bbox: tuple,
        points: np.ndarray,
        mode: str = "center",
    ) -> bool:
        """
        Kiểm tra một bounding box có nằm trong vùng đa giác zone hay không.

        Args:
            bbox (tuple/np.ndarray): Tọa độ khung nhận diện (x1, y1, x2, y2).
            points (np.ndarray): Mảng các đỉnh của đa giác zone (N, 2).
            mode (str): Chế độ kiểm tra: 
                - 'center': Dựa trên điểm tâm khung.
                - 'bottom_center': Dựa trên điểm giữa cạnh dưới.

        Returns:
            bool: True nếu điểm đại diện nằm trong hoặc trên cạnh zone.

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
        result = cv2.pointPolygonTest(points, point, measureDist=False)
        return result >= 0

    def _inference(self):
        """
        Thực hiện nhận diện và theo dõi đối tượng trên luồng dữ liệu đầu vào.

        Phương thức này cấu hình và chạy mô hình YOLO với bộ theo dõi ByteTrack 
        để phát hiện và duy trì định danh (ID) cho các đối tượng.

        Returns:
            Iterable: Trình tạo (generator) trả về kết quả nhận diện cho từng khung hình.
        """

        results = self.model.track(
            source=self.source,
            conf=self.conf,
            persist=True,
            tracker="bytetrack.yaml",
            show=False,
            stream=True,
            verbose=False,
            vid_stride=self.vid_stride,
        )

        return results

    def _parse_detections(self, boxes):
        """
        Trích xuất thông tin Bounding Box, Confidence và ID từ đối tượng boxes của YOLO.
        
        Args:
            boxes: Đối tượng kết quả trả về từ YOLO chứa thông tin nhận diện.
            
        Returns:
            tuple: (bboxes, confs, ids)
                - bboxes (np.ndarray): Mảng numpy chứa tọa độ bounding box (N, 4).
                - confs (np.ndarray): Mảng numpy chứa độ tin cậy của mỗi dự đoán (N,).
                - ids (np.ndarray): Mảng numpy chứa ID của đối tượng (N,). Gán -1 nếu không có ID.
        """
        if boxes is not None and len(boxes) > 0:
            bboxes = boxes.xyxy.cpu().numpy()   # (N, 4)
            confs  = boxes.conf.cpu().numpy()   # (N,)
            
            if boxes.id is not None:
                ids = boxes.id.cpu().numpy().astype(int)
                ids = ids % 999  # Giới hạn ID tối đa để tránh quá lớn
            else:
                ids = np.full((len(bboxes),), -1, dtype=int)
        else:
            bboxes = np.empty((0, 4), dtype=np.float32)
            confs  = np.empty((0,),   dtype=np.float32)
            ids    = np.empty((0,),   dtype=int)
            
        return bboxes, confs, ids

    def _assign_ids_to_zones(self, bboxes, ids):
        """
        Gắn từng đối tượng phát hiện được vào các vùng giám sát tương ứng.
        
        Mỗi bounding box sẽ được kiểm tra xem điểm đại diện của nó có nằm trong bất kỳ zone nào không.
        Giả định mỗi người chỉ nằm trong tối đa một vùng giám sát (sẽ ngừng kiểm tra khi đã tìm thấy).
        
        Args:
            bboxes (np.ndarray): Mảng tọa độ bounding box.
            ids (np.ndarray): Mảng ID tương ứng.
            
        Returns:
            tuple: (zone_names, zone_current_ids)
                - zone_names (List[Optional[str]]): Tên vùng zone chứa bbox tương ứng, hoặc None nếu nằm ngoài.
                - zone_current_ids (dict): Từ điển map tên zone với danh sách ID đang nằm trong zone đó.
        """
        # Tạo 1 list để lưu tên zone tương ứng với từng bbox
        zone_names: List[Optional[str]] = [None] * len(bboxes)

        # Dictionary chứa danh sách các ID đang nằm trong từng zone
        zone_current_ids = {zone.name: [] for zone in self.zones}

        if len(bboxes) > 0:
            for i, (bbox, obj_id) in enumerate(zip(bboxes, ids)):
                # Kiểm tra bbox này thuộc zone nào
                for zone in self.zones:
                    if self._is_bbox_in_zone(bbox, zone.pts, mode=self.zone_check_mode):
                        zone_names[i] = zone.name
                        zone_current_ids[zone.name].append(obj_id)
                        break # Ngừng kiểm tra vì 1 người chỉ ngồi 1 ghế

        return zone_names, zone_current_ids

    def _update_global_tracking(self, ids, zone_names, current_time):
        """
        Cập nhật hệ thống theo dõi ID toàn cục (Global Tracker).
        
        Ghi nhận vòng đời của mọi ID xuất hiện trên camera để phân biệt người mới 
        và người cũ bị che khuất (occlusion). Dọn dẹp (Garbage Collection) các ID đã mất dấu quá lâu.
        
        Args:
            ids (np.ndarray): Mảng ID hiện tại trên khung hình.
            zone_names (List[Optional[str]]): Tên vùng zone mà mỗi ID đang đứng (để biết nơi khai sinh).
            current_time (float): Mốc thời gian hệ thống hiện tại.
        """
        for obj_id, zone_name in zip(ids, zone_names):
            if obj_id == -1: continue # Bỏ qua ID không hợp lệ
            
            if obj_id not in self.global_tracked_ids:
                # Lần đầu tiên nhìn thấy ID này trên toàn camera
                self.global_tracked_ids[obj_id] = TrackedPerson(
                    id=obj_id,
                    first_seen_time=current_time,
                    first_seen_in_zone=zone_name, # Nếu đang đứng ngoài, nó sẽ lưu là None
                    last_seen_time=current_time
                )
            else:
                # ID cũ, chỉ cần update thời gian để không bị dọn rác
                self.global_tracked_ids[obj_id].last_seen_time = current_time

        # Dọn rác: Xóa những ID đã khuất bóng khỏi camera quá 15s để nhẹ RAM
        expired_ids = [k for k, v in self.global_tracked_ids.items() 
                       if current_time - v.last_seen_time > self.ID_GARBAGE_COLLECT_TIME]
        for k in expired_ids:
            del self.global_tracked_ids[k]

    def _update_zone_states(self, zone_current_ids, current_time):
        """
        Cập nhật trạng thái (State Machine) cho từng vùng giám sát và tạo payload gửi UART.
        
        Logic xử lý các trạng thái:
        - EMPTY: Ghế trống. Nếu có người vào -> chuyển sang PENDING_ENTER.
        - PENDING_ENTER: Chờ đủ thời gian xác nhận ngồi (CONFIRM_ENTER_TIME). Nếu đủ -> OCCUPIED.
        - OCCUPIED: Đã xác nhận có người. Nếu mất dấu -> chuyển sang PENDING_EXIT.
        - PENDING_EXIT: Chờ đủ thời gian mất dấu hoàn toàn (CONFIRM_EXIT_TIME) để báo EMPTY. 
          Nếu trong thời gian này YOLO tự nối lại ID hoặc có ID mới 'khai sinh' tại chỗ -> OCCUPIED.
          
        Args:
            zone_current_ids (dict): Từ điển chứa các ID đang nằm trong từng vùng.
            current_time (float): Mốc thời gian hệ thống hiện tại.
            
        Returns:
            dict: Payload UART gồm hai danh sách "detected" và "cleared" chứa sự kiện gửi đi.
        """
        uart_payload = {
            "detected": [],
            "cleared": []
        }

        for zone in self.zones:
            # Lấy các ID hợp lệ đang ở trong vùng này (bỏ qua ID = -1)
            valid_ids_in_zone = [i for i in zone_current_ids[zone.name] if i != -1]

            # LOGIC 1: ĐANG TRỐNG -> CÓ NGƯỜI VÀO
            if zone.state == ZoneState.EMPTY:
                if valid_ids_in_zone:
                    zone.current_id = valid_ids_in_zone[0]
                    zone.state = ZoneState.PENDING_ENTER
                    zone.enter_time = current_time

            # LOGIC 2: ĐANG CHỜ ĐỦ 10S
            elif zone.state == ZoneState.PENDING_ENTER:
                if zone.current_id in valid_ids_in_zone:
                    if current_time - zone.enter_time >= self.CONFIRM_ENTER_TIME:
                        zone.state = ZoneState.OCCUPIED
                        uart_payload["detected"].append({
                            "zone_name": zone.name,
                            "goal_pose": zone.goal_pose
                        })
                else:
                    zone.reset_zone()

            # LOGIC 3: ĐÃ XÁC NHẬN NGỒI
            elif zone.state == ZoneState.OCCUPIED:
                if zone.current_id in valid_ids_in_zone:
                    pass
                else:
                    zone.previous_state = ZoneState.OCCUPIED
                    zone.state = ZoneState.PENDING_EXIT
                    zone.lost_time = current_time

            # LOGIC 4: ĐANG CHỜ XÁC NHẬN RỜI ĐI HOẶC NỐI ID
            elif zone.state == ZoneState.PENDING_EXIT:

                # TRƯỜNG HỢP A: CÓ MỘT ID ĐANG XUẤT HIỆN TRONG GHẾ
                if valid_ids_in_zone:
                    new_id = valid_ids_in_zone[0]
                    
                    # Case A.1: Vẫn là ID cũ (YOLO tự nối lại được tracking)
                    if new_id == zone.current_id:
                        zone.state = zone.previous_state

                    # Case A.2: Là một ID lạ
                    else:
                        person_info = self.global_tracked_ids.get(new_id)
                        
                        # Nếu ID lạ này "khai sinh" ngay chính giữa cái ghế này -> Người cũ xuất hiện trở lại
                        if person_info and person_info.first_seen_in_zone == zone.name:
                            zone.current_id = new_id         # Gán ID mới cho họ
                            zone.state = zone.previous_state # Khôi phục OCCUPIED
                            
                        # Nếu ID lạ này "khai sinh" ở ngoài (hoặc ghế khác) rồi bước vào -> Người mới
                        else:
                            # 1. Gửi lệnh chốt báo người cũ ĐÃ ĐI
                            uart_payload["cleared"].append({
                                "zone_name": zone.name,
                                "goal_pose": zone.goal_pose
                            })
                            
                            # 2. Xóa thông tin người cũ, cho người mới bắt đầu đếm 10s PENDING_ENTER luôn
                            zone.reset_zone()
                            zone.current_id = new_id
                            zone.state = ZoneState.PENDING_ENTER
                            zone.enter_time = current_time

                # TRƯỜNG HỢP B: VẪN KHÔNG THẤY AI (BẮT ĐẦU ĐẾM NGƯỢC)
                else:
                    if current_time - zone.lost_time >= self.CONFIRM_EXIT_TIME:
                        # Đã quá 5s không có ai xuất hiện -> Chính thức báo trống
                        uart_payload["cleared"].append({
                            "zone_name": zone.name,
                            "goal_pose": zone.goal_pose
                        })
                        zone.reset_zone()

        return uart_payload

    def _push_websocket_data(self, frame, bboxes, confs, ids):
        """Đẩy dữ liệu bboxes qua WebSocket bằng cách lưu vào biến class."""
        h, w = frame.shape[:2]
        objects_data = []
        
        for bbox, conf, obj_id in zip(bboxes, confs, ids):
            if obj_id == -1: continue # Bỏ qua người chưa được ByteTrack gán ID
            
            x1, y1, x2, y2 = bbox[:4]
            
            # Chuẩn hóa tọa độ (0.0 - 1.0) cho Frontend
            objects_data.append({
                "id": int(obj_id),
                "bbox": [float(x1/w), float(y1/h), float((x2-x1)/w), float((y2-y1)/h)],
                "conf": float(conf)
            })
        
        # Đóng gói JSON
        self.latest_ws_payload = {
            "timestamp": int(time.time() * 1000),
            "resolution": {"width": w, "height": h},
            "count": len(objects_data),
            "objects": objects_data,
            "zones": {zone.name: zone.state.value for zone in self.zones}
        }

    def sync_uart(self):
        """Gửi lại dữ liệu UART gần nhất khi nhận được lệnh sync."""
        if self.latest_uart_payload:
            self._send_uart_payload(self.latest_uart_payload, is_sync=True)
            LOGGER.info("Đã gửi lại dữ liệu UART gần nhất theo lệnh sync.")
        else:
            LOGGER.info("Không có dữ liệu UART nào trước đó để gửi lại.")

    def _send_uart_payload(self, payload: dict, is_sync: bool = False):
        """Chuyển đổi dữ liệu sang định dạng string d:kv...-c:kv... và chia nhỏ nếu vượt quá 250 bytes"""
        if not payload or not hasattr(self, 'uart'):
            return
            
        detected = payload.get("detected", [])
        cleared = payload.get("cleared", [])
        
        # Hàm phụ đóng gói chuỗi
        def build_string(det_list, clr_list, is_sync_flag):
            parts = []
            if is_sync_flag:
                parts.append("sync")
                
            if det_list:
                d_str = "d:" + ";".join([f"{item['zone_name']},{item['goal_pose'].get('x',0)},{item['goal_pose'].get('y',0)},{item['goal_pose'].get('theta',0)}" for item in det_list])
                parts.append(d_str)
            if clr_list:
                c_str = "c:" + ";".join([f"{item['zone_name']},{item['goal_pose'].get('x',0)},{item['goal_pose'].get('y',0)},{item['goal_pose'].get('theta',0)}" for item in clr_list])
                parts.append(c_str)
            return "-".join(parts)

        MAX_BYTES = 250
        all_events = [("d", d) for d in detected] + [("c", c) for c in cleared]
        
        current_det = []
        current_clr = []
        
        for event_type, event_data in all_events:
            # Thêm tạm vào nhóm hiện tại
            if event_type == "d":
                current_det.append(event_data)
            else:
                current_clr.append(event_data)
                
            test_str = build_string(current_det, current_clr, is_sync)
            
            # Nếu vượt quá số bytes giới hạn, gửi lô cũ trước
            if len(test_str.encode('utf-8')) > MAX_BYTES:
                # Nhả event vừa thêm ra để lấy chuỗi an toàn
                if event_type == "d":
                    current_det.pop()
                else:
                    current_clr.pop()
                    
                full_str = build_string(current_det, current_clr, is_sync)
                if full_str:
                    threading.Thread(target=self.uart.send_string, args=(full_str,), daemon=True).start()
                    time.sleep(0.02) # Nháy chậm lại xíu tránh tràn buffer bên nhận
                    
                # Bắt đầu mẻ mới với đồ đạc vừa bị loại ra
                current_det = [event_data] if event_type == "d" else []
                current_clr = [event_data] if event_type == "c" else []
        
        # Gửi mẻ cuối (hoặc mẻ duy nhất nếu tổng dữ liệu nhỏ)
        final_str = build_string(current_det, current_clr, is_sync)
        if final_str:
            threading.Thread(target=self.uart.send_string, args=(final_str,), daemon=True).start()

    def _cleanup_run(self):
        """Dọn dẹp tài nguyên sau khi dừng vòng lặp run (RTSP stream, tracker, GUI)."""
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
            
            # Xóa predictor để ultralytics tạo mới hoàn toàn khi gọi model.track() lần sau
            try:
                self.model.predictor = None
                LOGGER.info("Đã xóa predictor (sẽ tạo mới khi start lại).")
            except Exception:
                pass

        # 3. Reset trạng thái các zone về EMPTY
        for zone in self.zones:
            zone.reset_zone()
        self.global_tracked_ids = {}

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

                # speed_dict = result.speed
                # inference_time = speed_dict['inference']
                
                frame = result.orig_img.copy()

                # 1. Trích xuất thông tin Bounding Box
                bboxes, confs, ids = self._parse_detections(result.boxes)

                # 2. Gắn ID vào các vùng zones
                zone_names, zone_current_ids = self._assign_ids_to_zones(bboxes, ids)
                
                # 3. Cập nhật Global Tracker
                current_time = time.time()
                self._update_global_tracking(ids, zone_names, current_time)

                # 4. State Machine: Cập nhật trạng thái từng vùng
                uart_payload = self._update_zone_states(zone_current_ids, current_time)

                # 5. Đẩy dữ liệu WebSocket cho web preview
                self._push_websocket_data(frame, bboxes, confs, ids)

                # 6. Gửi dữ liệu qua UART
                if uart_payload["detected"] or uart_payload["cleared"]:
                    self.latest_uart_payload = uart_payload
                    self._send_uart_payload(uart_payload)
                    total_events = len(uart_payload["detected"]) + len(uart_payload["cleared"])
                    # LOGGER.info(f"Đã gộp gửi {total_events} sự kiện qua UART.")

                # Tính FPS
                current_time = time.time()
                fps = 1.0 / (current_time - prev_time)
                prev_time = current_time

                # Verbose log
                if self.verbose:
                    LOGGER.info(f"FPS: {fps:.1f}")

                if self.show:
                    # Vẽ các vùng giám sát
                    frame = self._draw_zones(frame)

                    # Vẽ các đối tượng được phát hiện
                    frame = self._draw_overlay(frame, bboxes, confs, ids, zone_names)

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
            # Dọn dẹp tài nguyên: đóng RTSP stream, reset tracker, đóng GUI
            self._cleanup_run()
            LOGGER.info("HumanDetector Đã dừng.")