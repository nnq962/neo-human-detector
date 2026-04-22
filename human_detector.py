import os
import aidcv as cv2
import numpy as np
from typing import List, Optional
from ultralytics import YOLO
from utils import LOGGER, uart_manager
import time
import threading
from models import ROIState, SeatZone, TrackedPerson
import queue

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

    COLOR_BBOX_NORMAL = (255, 0, 0)    # xanh dương — bbox ngoài ROI
    COLOR_BBOX_IN_ROI = (0, 200, 0)    # xanh lá   — bbox trong ROI

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
        display_scale: float = 1.0,
        ws_queue: queue.Queue = None
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
        self.display_scale = display_scale
        self.ws_queue = ws_queue

        # Log info
        LOGGER.info(f"Source: {source}")
        LOGGER.info(f"Conf: {conf}")
        LOGGER.info(f"Imgsz: {imgsz}")
        LOGGER.info(f"Device: {device}")
        LOGGER.info(f"Half: {half}")
        LOGGER.info(f"Show: {show}")
        LOGGER.info(f"ROI Check Mode: {roi_check_mode}")        
        LOGGER.info(f"Display Scale: {display_scale}")        

        # Initialize monitored areas -------------------------------------------------------------------------
        if monitored_areas is None:
            raise ValueError("monitored_areas must not be None")

        self.monitored_areas = monitored_areas
        self.zones = {} 

        for area in self.monitored_areas:
            name = area["name"]
            # Ép kiểu numpy array ngay tại đây
            pts = np.array(area["pts"], dtype=np.int32) if not isinstance(area["pts"], np.ndarray) else area["pts"]
            
            # Khởi tạo Object SeatZone
            self.zones[name] = SeatZone(
                name=name,
                pts=pts,
                slam_pose=area.get("slam_pose", {})
            )

        # Global ID Tracker
        self.global_tracked_ids = {}

        # Time Thresholds
        self.CONFIRM_ENTER_TIME = 10.0      # Ngồi liên tục > 10s mới tính là OCCUPIED
        self.CONFIRM_EXIT_TIME = 8.0        # Mất dấu > 8s mới tính là EMPTY
        self.ID_GARBAGE_COLLECT_TIME = 5.0 # Quá 5s không thấy ID trên toàn camera -> Dọn rác
        # -----------------------------------------------------------------------------------------------------

        # Load model
        self.model = YOLO(
            self.DEFAULT_MODELS, 
            task="detect"
        )

        # Khởi tạo UART Manager để gửi dữ liệu
        self.uart = uart_manager

    def update_dynamic_config(
        self, 
        new_conf: float = None, 
        new_roi_check_mode: str = None,
        new_monitored_areas: List[dict] = None
    ) -> bool:
        """
        Cập nhật cấu hình động (Hot Reload) cho hệ thống trong lúc đang chạy.

        Args:
            new_conf (float, optional): Ngưỡng độ tin cậy mới (0.0 - 1.0).
            new_roi_check_mode (str, optional): Chế độ kiểm tra vùng đại diện mới ('center' hoặc 'bottom_center').
            new_monitored_areas (List[dict], optional): Danh sách cấu hình các vùng giám sát (ROI) mới.

        Returns:
            bool: Trạng thái cập nhật thành công (luôn trả về True nếu không có ngoại lệ).
        """
        if new_conf is not None:
            self.conf = float(new_conf)
            LOGGER.info(f"Đã cập nhật ngưỡng Conf: {self.conf}")

        if new_roi_check_mode is not None:
            if new_roi_check_mode in ("center", "bottom_center"):
                self.roi_check_mode = new_roi_check_mode
                LOGGER.info(f"Đã cập nhật ROI Check Mode: {self.roi_check_mode}")

        if new_monitored_areas is not None:
            self.monitored_areas = new_monitored_areas
            
            # Tạo một dictionary tạm thời để build các vùng mới trước
            temp_zones = {}
            for area in self.monitored_areas:
                name = area["name"]
                pts = np.array(area["pts"], dtype=np.int32) if not isinstance(area["pts"], np.ndarray) else area["pts"]
                temp_zones[name] = SeatZone(
                    name=name,
                    pts=pts,
                    slam_pose=area.get("slam_pose", {})
                )
            
            # Gán đè 1 lần duy nhất để thay thế dictionary cũ. 
            # Việc này trên Python là Atomic (cực kỳ an toàn không làm crash vòng lặp)
            self.zones = temp_zones
            
            # Reset lại tracking cho an toàn với vùng mới (Dùng phép gán để đảm bảo Atomic)
            self.global_tracked_ids = {}
            
            LOGGER.info("Đã cập nhật ROI thành công!")

        return True

    def _draw_monitored_areas(
        self,
        frame: np.ndarray,
    ) -> np.ndarray:
        """
        Vẽ lớp phủ các vùng giám sát (ROI) lên khung hình.
        Sử dụng màu sắc tương ứng với trạng thái của từng vùng dựa trên ROIColor.

        Args:
            frame (np.ndarray): Khung hình ảnh gốc (hệ màu BGR).

        Returns:
            np.ndarray: Khung hình đã được chèn các hiệu ứng hình ảnh của ROI.
        """

        overlay = frame.copy()
        for zone in self.zones.values():
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

    def _draw_detections(
        self,
        frame: np.ndarray,
        bboxes: np.ndarray,
        confs: np.ndarray,
        ids: np.ndarray,
        bbox_roi_names: List[Optional[str]],
    ) -> np.ndarray:
        """
        Vẽ khung nhận diện (Bounding Box) và thông tin đối tượng lên khung hình.
        Hiển thị ID, độ tin cậy và điểm số tín nhiệm nếu đối tượng thuộc vùng giám sát.

        Args:
            frame (np.ndarray): Khung hình ảnh gốc (BGR).
            bboxes (np.ndarray): Mảng tọa độ các khung nhận diện (N, 4).
            confs (np.ndarray): Mảng giá trị độ tin cậy (N,).
            ids (np.ndarray): Mảng ID của các đối tượng (N,).
            bbox_roi_names (List[Optional[str]]): Danh sách tên ROI tương ứng của mỗi đối tượng.

        Returns:
            np.ndarray: Khung hình đã được vẽ thông tin nhận diện.
        """

        for bbox, conf, obj_id, roi_name in zip(bboxes, confs, ids, bbox_roi_names):
            x1, y1, x2, y2 = map(int, bbox[:4])
            in_roi = roi_name is not None
            color  = self.COLOR_BBOX_IN_ROI if in_roi else self.COLOR_BBOX_NORMAL

            # Vẽ bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness=2)

            # Tạo label: luôn hiện id, conf, thêm tên ROI nếu trong vùng
            id_text = f"ID {obj_id}" if obj_id != -1 else "ID:?"
            if in_roi:
                # Nếu nằm trong ROI, hiện tên ROI
                label = f"[{id_text}] [{conf:.2f}] [{roi_name}]"
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

    def _send_uart_payload(self, payload: dict):
        """Chuyển đổi dữ liệu sang định dạng string d:kv...-c:kv... và chia nhỏ nếu vượt quá 250 bytes"""
        if not payload or not hasattr(self, 'uart'):
            return
            
        detected = payload.get("detected", [])
        cleared = payload.get("cleared", [])
        
        # Hàm phụ đóng gói chuỗi
        def build_string(det_list, clr_list):
            parts = []
            if det_list:
                d_str = "d:" + ";".join([f"{item['area_name']},{item['slam_pose'].get('x',0)},{item['slam_pose'].get('y',0)},{item['slam_pose'].get('theta',0)}" for item in det_list])
                parts.append(d_str)
            if clr_list:
                c_str = "c:" + ";".join([f"{item['area_name']},{item['slam_pose'].get('x',0)},{item['slam_pose'].get('y',0)},{item['slam_pose'].get('theta',0)}" for item in clr_list])
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
                
            test_str = build_string(current_det, current_clr)
            
            # Nếu vượt quá số bytes giới hạn, gửi lô cũ trước
            if len(test_str.encode('utf-8')) > MAX_BYTES:
                # Nhả event vừa thêm ra để lấy chuỗi an toàn
                if event_type == "d":
                    current_det.pop()
                else:
                    current_clr.pop()
                    
                full_str = build_string(current_det, current_clr)
                if full_str:
                    threading.Thread(target=self.uart.send_string, args=(full_str,), daemon=True).start()
                    time.sleep(0.02) # Nháy chậm lại xíu tránh tràn buffer bên nhận
                    
                # Bắt đầu mẻ mới với đồ đạc vừa bị loại ra
                current_det = [event_data] if event_type == "d" else []
                current_clr = [event_data] if event_type == "c" else []
        
        # Gửi mẻ cuối (hoặc mẻ duy nhất nếu tổng dữ liệu nhỏ)
        final_str = build_string(current_det, current_clr)
        if final_str:
            threading.Thread(target=self.uart.send_string, args=(final_str,), daemon=True).start()

    def inference(self):
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
            imgsz=self.imgsz,
            device=self.device,
            half=self.half,
            show=False,
            stream=True,
            verbose=False,
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
            else:
                ids = np.full((len(bboxes),), -1, dtype=int)
        else:
            bboxes = np.empty((0, 4), dtype=np.float32)
            confs  = np.empty((0,),   dtype=np.float32)
            ids    = np.empty((0,),   dtype=int)
            
        return bboxes, confs, ids

    def _assign_ids_to_rois(self, bboxes, ids):
        """
        Gắn từng đối tượng phát hiện được vào các vùng giám sát (ROI) tương ứng.
        
        Mỗi bounding box sẽ được kiểm tra xem điểm đại diện của nó có nằm trong bất kỳ ROI nào không.
        Giả định mỗi người chỉ nằm trong tối đa một vùng giám sát (sẽ ngừng kiểm tra khi đã tìm thấy).
        
        Args:
            bboxes (np.ndarray): Mảng tọa độ bounding box.
            ids (np.ndarray): Mảng ID tương ứng.
            
        Returns:
            tuple: (bbox_roi_names, roi_current_ids)
                - bbox_roi_names (List[Optional[str]]): Tên vùng ROI chứa bbox tương ứng, hoặc None nếu nằm ngoài.
                - roi_current_ids (dict): Từ điển map tên ROI với danh sách ID đang nằm trong ROI đó.
        """
        # Tạo 1 list để lưu tên ROI tương ứng với từng bbox
        bbox_roi_names: List[Optional[str]] = [None] * len(bboxes)

        # Dictionary chứa danh sách các ID đang nằm trong từng ROI
        roi_current_ids = {zone_name: [] for zone_name in self.zones.keys()}

        if len(bboxes) > 0:
            for i, (bbox, obj_id) in enumerate(zip(bboxes, ids)):
                for zone_name, zone in self.zones.items():
                    if self.is_bbox_in_roi(bbox, zone.pts, mode=self.roi_check_mode):
                        bbox_roi_names[i] = zone_name
                        roi_current_ids[zone_name].append(obj_id)
                        break # Ngừng kiểm tra vì 1 người chỉ ngồi 1 ghế

        return bbox_roi_names, roi_current_ids

    def _update_global_tracking(self, ids, bbox_roi_names, current_time):
        """
        Cập nhật hệ thống theo dõi ID toàn cục (Global Tracker).
        
        Ghi nhận vòng đời của mọi ID xuất hiện trên camera để phân biệt người mới 
        và người cũ bị che khuất (occlusion). Dọn dẹp (Garbage Collection) các ID đã mất dấu quá lâu.
        
        Args:
            ids (np.ndarray): Mảng ID hiện tại trên khung hình.
            bbox_roi_names (List[Optional[str]]): Tên vùng ROI mà mỗi ID đang đứng (để biết nơi khai sinh).
            current_time (float): Mốc thời gian hệ thống hiện tại.
        """
        for obj_id, roi_name in zip(ids, bbox_roi_names):
            if obj_id == -1: continue # Bỏ qua ID không hợp lệ
            
            if obj_id not in self.global_tracked_ids:
                # Lần đầu tiên nhìn thấy ID này trên toàn camera
                self.global_tracked_ids[obj_id] = TrackedPerson(
                    id=obj_id,
                    first_seen_time=current_time,
                    first_seen_in_roi=roi_name, # Nếu đang đứng ngoài, nó sẽ lưu là None
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

    def _update_zone_states(self, roi_current_ids, current_time):
        """
        Cập nhật trạng thái (State Machine) cho từng vùng giám sát và tạo payload gửi UART.
        
        Logic xử lý các trạng thái:
        - EMPTY: Ghế trống. Nếu có người vào -> chuyển sang PENDING_ENTER.
        - PENDING_ENTER: Chờ đủ thời gian xác nhận ngồi (CONFIRM_ENTER_TIME). Nếu đủ -> OCCUPIED.
        - OCCUPIED: Đã xác nhận có người. Nếu mất dấu -> chuyển sang PENDING_EXIT.
        - PENDING_EXIT: Chờ đủ thời gian mất dấu hoàn toàn (CONFIRM_EXIT_TIME) để báo EMPTY. 
          Nếu trong thời gian này YOLO tự nối lại ID hoặc có ID mới 'khai sinh' tại chỗ -> OCCUPIED.
          
        Args:
            roi_current_ids (dict): Từ điển chứa các ID đang nằm trong từng vùng.
            current_time (float): Mốc thời gian hệ thống hiện tại.
            
        Returns:
            dict: Payload UART gồm hai danh sách "detected" và "cleared" chứa sự kiện gửi đi.
        """
        uart_payload = {
            "detected": [],
            "cleared": []
        }

        for zone_name, zone in self.zones.items():
            # Lấy các ID hợp lệ đang ở trong vùng này (bỏ qua ID = -1)
            valid_ids_in_zone = [i for i in roi_current_ids[zone_name] if i != -1]

            # LOGIC 1: ĐANG TRỐNG -> CÓ NGƯỜI VÀO
            if zone.state == ROIState.EMPTY:
                if valid_ids_in_zone:
                    zone.current_id = valid_ids_in_zone[0]
                    zone.state = ROIState.PENDING_ENTER
                    zone.enter_time = current_time

            # LOGIC 2: ĐANG CHỜ ĐỦ 10S
            elif zone.state == ROIState.PENDING_ENTER:
                if zone.current_id in valid_ids_in_zone:
                    if current_time - zone.enter_time >= self.CONFIRM_ENTER_TIME:
                        zone.state = ROIState.OCCUPIED
                        uart_payload["detected"].append({
                            "area_name": zone_name,
                            "slam_pose": zone.slam_pose
                        })
                else:
                    zone.reset_zone()

            # LOGIC 3: ĐÃ XÁC NHẬN NGỒI
            elif zone.state == ROIState.OCCUPIED:
                if zone.current_id in valid_ids_in_zone:
                    pass
                else:
                    zone.previous_state = ROIState.OCCUPIED
                    zone.state = ROIState.PENDING_EXIT
                    zone.lost_time = current_time

            # LOGIC 4: ĐANG CHỜ XÁC NHẬN RỜI ĐI HOẶC NỐI ID
            elif zone.state == ROIState.PENDING_EXIT:

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
                        if person_info and person_info.first_seen_in_roi == zone_name:
                            zone.current_id = new_id         # Gán ID mới cho họ
                            zone.state = zone.previous_state # Khôi phục OCCUPIED
                            
                        # Nếu ID lạ này "khai sinh" ở ngoài (hoặc ghế khác) rồi bước vào -> Người mới
                        else:
                            # 1. Gửi lệnh chốt báo người cũ ĐÃ ĐI
                            uart_payload["cleared"].append({
                                "area_name": zone_name,
                                "slam_pose": zone.slam_pose
                            })
                            
                            # 2. Xóa thông tin người cũ, cho người mới bắt đầu đếm 10s PENDING_ENTER luôn
                            zone.reset_zone()
                            zone.current_id = new_id
                            zone.state = ROIState.PENDING_ENTER
                            zone.enter_time = current_time

                # TRƯỜNG HỢP B: VẪN KHÔNG THẤY AI (BẮT ĐẦU ĐẾM NGƯỢC)
                else:
                    if current_time - zone.lost_time >= self.CONFIRM_EXIT_TIME:
                        # Đã quá 5s không có ai xuất hiện -> Chính thức báo trống
                        uart_payload["cleared"].append({
                            "area_name": zone_name,
                            "slam_pose": zone.slam_pose
                        })
                        zone.reset_zone()

        return uart_payload

    def run(self):
        """
        Khởi chạy vòng lặp nhận diện và giám sát đối tượng theo thời gian thực.
        """
        win_name = f"HumanDetector"
        if self.show:
            cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)

        results = self.inference()
        prev_time = time.time()

        try:
            for result in results:
                # speed_dict = result.speed
                # inference_time = speed_dict['inference']
                
                frame = result.orig_img.copy()

                # 1. Trích xuất thông tin Bounding Box
                bboxes, confs, ids = self._parse_detections(result.boxes)

                # ==========================================
                # ĐẨY DỮ LIỆU WEBSOCKET
                # ==========================================
                if getattr(self, 'ws_queue', None) is not None:
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
                    ws_payload = {
                        "timestamp": int(time.time() * 1000),
                        "resolution": {"width": w, "height": h},
                        "objects": objects_data
                    }
                    
                    # Cập nhật Queue (Chiến thuật: Luôn giữ frame mới nhất)
                    if self.ws_queue.full():
                        try:
                            self.ws_queue.get_nowait() # Đẩy frame cũ ra
                        except queue.Empty:
                            pass
                    self.ws_queue.put(ws_payload) # Nhét frame mới vào
                # ==========================================

                # 2. Gắn ID vào các vùng ROI
                bbox_roi_names, roi_current_ids = self._assign_ids_to_rois(bboxes, ids)
                
                # 3. Cập nhật Global Tracker
                current_time = time.time()
                self._update_global_tracking(ids, bbox_roi_names, current_time)

                # 4. State Machine: Cập nhật trạng thái từng vùng
                uart_payload = self._update_zone_states(roi_current_ids, current_time)

                # 5. Gửi dữ liệu qua UART
                if uart_payload["detected"] or uart_payload["cleared"]:
                    self._send_uart_payload(uart_payload)
                    total_events = len(uart_payload["detected"]) + len(uart_payload["cleared"])
                    # LOGGER.info(f"Đã gộp gửi {total_events} sự kiện qua UART.")

                # Vẽ các vùng giám sát
                frame = self._draw_monitored_areas(
                    frame
                )

                # Vẽ các đối tượng được phát hiện
                frame = self._draw_detections(
                    frame, 
                    bboxes, 
                    confs, 
                    ids,
                    bbox_roi_names
                )

                # Tính FPS
                current_time = time.time()
                fps = 1.0 / (current_time - prev_time)
                prev_time = current_time

                if self.show:
                    if self.display_scale != 1.0:
                        # Thay đổi kích thước frame trước khi hiển thị để thu/phóng cửa sổ (workaround khi không dùng waitKey)
                        display_frame = cv2.resize(frame, None, fx=self.display_scale, fy=self.display_scale)
                        cv2.imshow(win_name, display_frame)
                    else:
                        cv2.imshow(win_name, frame)
                else:
                    LOGGER.info(f"FPS: {fps:.1f}")
                    pass

        except Exception as e:
            LOGGER.error(f"Lỗi xảy ra trong vòng lặp run: {e}", exc_info=True)

        finally:
            cv2.destroyAllWindows()
            if hasattr(self, 'uart'):
                self.uart.close()
            LOGGER.info("HumanDetector Đã dừng.")
            # Force-exit để tránh crash C++ runtime khi cleanup
            # RTSP stream hoặc GPU context (ultralytics/OpenCV known issue)
            os._exit(0)