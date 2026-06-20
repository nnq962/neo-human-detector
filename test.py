from src.media_sources import MediaSources


import argparse
import cv2
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", action="store_true", help="Show frames in a window")
    args = parser.parse_args()


    sources = ["rtsp://admin:0612232026camera@192.168.2.50:554/Streaming/Channels/101"] * 2

    # sources = [
    # "https://youtu.be/vCIc1g_4JWM?si=Bpb2kriUjQwaGQen",
    # "https://youtu.be/vCIc1g_4JWM?si=Bpb2kriUjQwaGQen",
    # ]

    # sources = ["examples/crowd.mp4", "examples/video.MP4"] * 2

    # sources = [0, 0, 0]

    target_h = 480

    with MediaSources(sources) as ms:
        for batch_idx, (frames, infos) in enumerate(ms):
            if args.show:
                resized_frames = resize_frames_to_height(frames, target_h)
                draw_frame_labels(resized_frames, infos)

                combined = np.hstack(resized_frames)
                cv2.imshow("Media Sources", combined)

                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
            else:
                frame_list = [
                    f"{info.source_type.name} {frame.shape[1]}x{frame.shape[0]}"
                    for frame, info in zip(frames, infos)
                ]
                print(f"Batch {batch_idx}: [{', '.join(frame_list)}]")

    if args.show:
        cv2.destroyAllWindows()


def resize_frames_to_height(frames: list[np.ndarray], target_h: int) -> list[np.ndarray]:
    resized_frames = []

    for frame in frames:
        h, w = frame.shape[:2]
        new_w = int(w * target_h / h)
        resized_frame = cv2.resize(frame, (new_w, target_h))
        resized_frames.append(resized_frame)

    return resized_frames


def draw_frame_labels(frames: list[np.ndarray], infos) -> None:
    for i, (frame, info) in enumerate(zip(frames, infos)):
        label = f"[{i}] {info.source_type.name} {info.resolution[0]}x{info.resolution[1]}"

        cv2.putText(
            frame,
            label,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
        )


if __name__ == "__main__":
    main()