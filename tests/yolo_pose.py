import cv2
import time
import argparse
from urllib.parse import quote

from ultralytics import YOLO


KEYPOINT_NAMES = {
    0: "nose",
    1: "left_eye",
    2: "right_eye",
    3: "left_ear",
    4: "right_ear",
    5: "left_shoulder",
    6: "right_shoulder",
    7: "left_elbow",
    8: "right_elbow",
    9: "left_wrist",
    10: "right_wrist",
    11: "left_hip",
    12: "right_hip",
    13: "left_knee",
    14: "right_knee",
    15: "left_ankle",
    16: "right_ankle",
}


def build_rtsp_url():
    username = "admin"
    password = "061223@bC"

    # Encode ký tự đặc biệt trong password, ví dụ @ -> %40
    password_encoded = quote(password, safe="")

    host = "192.168.0.10"
    port = 554
    path = "Streaming/Channels/101"

    return f"rtsp://{username}:{password_encoded}@{host}:{port}/{path}"


def midpoint(p1, p2):
    return (
        int((p1[0] + p2[0]) / 2),
        int((p1[1] + p2[1]) / 2),
    )


def get_seat_point(kpts_xy, kpts_conf, bbox, min_conf=0.3):
    """
    Ưu tiên lấy điểm đại diện người ngồi:
    1. hip center
    2. shoulder center
    3. fallback về lower-center bbox
    """
    x1, y1, x2, y2 = bbox

    # left_hip = 11, right_hip = 12
    if kpts_conf[11] > min_conf and kpts_conf[12] > min_conf:
        p = midpoint(kpts_xy[11], kpts_xy[12])
        return p, "hip"

    # left_shoulder = 5, right_shoulder = 6
    if kpts_conf[5] > min_conf and kpts_conf[6] > min_conf:
        p = midpoint(kpts_xy[5], kpts_xy[6])
        return p, "shoulder"

    # fallback bbox
    px = int((x1 + x2) / 2)
    py = int(y1 + 0.65 * (y2 - y1))
    return (px, py), "bbox"


def draw_keypoints(frame, kpts_xy, kpts_conf, min_conf=0.3):
    # Skeleton COCO cơ bản
    skeleton = [
        (5, 6),    # shoulders
        (5, 7),    # left arm
        (7, 9),
        (6, 8),    # right arm
        (8, 10),
        (5, 11),   # body
        (6, 12),
        (11, 12),  # hips
        (11, 13),  # left leg
        (13, 15),
        (12, 14),  # right leg
        (14, 16),
    ]

    for i, (x, y) in enumerate(kpts_xy):
        if kpts_conf[i] > min_conf:
            cv2.circle(frame, (int(x), int(y)), 4, (0, 255, 255), -1)

    for a, b in skeleton:
        if kpts_conf[a] > min_conf and kpts_conf[b] > min_conf:
            ax, ay = kpts_xy[a]
            bx, by = kpts_xy[b]
            cv2.line(
                frame,
                (int(ax), int(ay)),
                (int(bx), int(by)),
                (0, 255, 0),
                2,
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-m", "-model", "--model", default="yolo26m-pose.pt")
    parser.add_argument("--conf", type=float, default=0.35)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default=0, help="0 for GPU, cpu for CPU")
    parser.add_argument("--show-keypoints", action="store_true")
    args = parser.parse_args()

    rtsp_url = build_rtsp_url()

    print("Loading model:", args.model)
    model = YOLO(args.model)

    print("Opening RTSP stream...")
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

    # Giảm buffer để đỡ delay
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print("Không mở được RTSP stream.")
        print("Hãy kiểm tra lại:")
        print("- Camera có cùng mạng không")
        print("- Username/password đúng không")
        print("- RTSP URL có encode ký tự @ chưa")
        print("- Có mở được bằng VLC chưa")
        return

    prev_time = time.time()

    while True:
        ret, frame = cap.read()

        if not ret:
            print("Không đọc được frame từ camera, thử reconnect...")
            cap.release()
            time.sleep(1)
            cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            continue

        results = model.predict(
            frame,
            conf=args.conf,
            imgsz=args.imgsz,
            device=args.device,
            verbose=False,
        )

        result = results[0]

        person_count = 0

        if result.boxes is not None and result.keypoints is not None:
            boxes = result.boxes.xyxy.cpu().numpy()
            confs = result.boxes.conf.cpu().numpy()

            kpts_xy = result.keypoints.xy.cpu().numpy()
            kpts_conf = result.keypoints.conf.cpu().numpy()

            for i, box in enumerate(boxes):
                x1, y1, x2, y2 = map(int, box)
                person_conf = confs[i]
                person_count += 1

                current_kpts_xy = kpts_xy[i]
                current_kpts_conf = kpts_conf[i]

                seat_point, point_type = get_seat_point(
                    current_kpts_xy,
                    current_kpts_conf,
                    (x1, y1, x2, y2),
                    min_conf=0.3,
                )

                # Vẽ bbox
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 128, 0), 2)

                label = f"person {person_conf:.2f} | {point_type}"
                cv2.putText(
                    frame,
                    label,
                    (x1, max(y1 - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 128, 0),
                    2,
                )

                # Vẽ keypoints nếu muốn xem kỹ
                if args.show_keypoints:
                    draw_keypoints(
                        frame,
                        current_kpts_xy,
                        current_kpts_conf,
                        min_conf=0.3,
                    )

                # Vẽ điểm đại diện để check ghế
                cv2.circle(frame, seat_point, 8, (0, 0, 255), -1)
                cv2.putText(
                    frame,
                    point_type,
                    (seat_point[0] + 8, seat_point[1] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 0, 255),
                    2,
                )

        now = time.time()
        fps = 1.0 / max(now - prev_time, 1e-6)
        prev_time = now

        cv2.putText(
            frame,
            f"FPS: {fps:.1f} | Persons: {person_count}",
            (20, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 255, 255),
            2,
        )

        cv2.imshow("YOLO Pose RTSP Test", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
