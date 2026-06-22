from pathlib import Path

from ultralytics import YOLO


RTSP_URLS = [
    "rtsp://admin:061223%40bC@192.168.0.15:554/Streaming/Channels/101",
    "rtsp://admin:061223%40bC@192.168.0.10:554/Streaming/Channels/101",
]

STREAMS_FILE = "sources.streams"
MODEL_PATH = "yolo26m-pose.pt"


def main():
    Path(STREAMS_FILE).write_text("\n".join(RTSP_URLS), encoding="utf-8")

    model = YOLO(MODEL_PATH)

    results = model.track(
        source=STREAMS_FILE,
        conf=0.5,
        classes=[0],          # person
        stream=True,
        tracker="bytetrack.yaml",
        persist=True,
        show=True,            # để Ultralytics tự vẽ + tự show
        verbose=True,
    )

    for _ in results:
        pass


if __name__ == "__main__":
    main()