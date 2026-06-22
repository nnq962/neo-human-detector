import cv2
from ultralytics import YOLO


RTSP_URL = "rtsp://admin:061223%40bC@192.168.0.15:554/Streaming/Channels/101"
MODEL_PATH = "yolo26m.pt"


def main():
    model = YOLO(MODEL_PATH)

    cap = cv2.VideoCapture(RTSP_URL)

    if not cap.isOpened():
        raise RuntimeError("Không mở được RTSP stream")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Không đọc được frame")
            break

        results = model(
            frame,
            classes=[0],      # COCO class 0 = person
            conf=0.5,
            verbose=False
        )

        annotated_frame = results[0].plot()

        cv2.imshow("YOLO11m Person Detection", annotated_frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()