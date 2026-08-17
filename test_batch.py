# test_batch.py

import time
import numpy as np

# TensorRT 8.5 compatibility
if "bool" not in np.__dict__:
    np.bool = bool

from ultralytics import YOLO


MODEL = "weights/tensorRT/yolo/yolo26/pose/yolo26s-pose.engine"
IMGSZ = 640
WARMUP = 10
ITERATIONS = 100


def benchmark(model, batch_size):
    # Giả lập frame camera Full HD
    frames = [
        np.random.randint(
            0, 256,
            (1080, 1920, 3),
            dtype=np.uint8,
        )
        for _ in range(batch_size)
    ]

    print(f"\n{'=' * 60}")
    print(f"BATCH SIZE = {batch_size}")
    print(f"{'=' * 60}")

    # Warmup
    print("Warming up...")

    for _ in range(WARMUP):
        model.predict(
            frames,
            imgsz=IMGSZ,
            device=0,
            verbose=False,
        )

    # Benchmark
    times = []

    for _ in range(ITERATIONS):
        start = time.perf_counter()

        results = model.predict(
            frames,
            imgsz=IMGSZ,
            device=0,
            verbose=False,
        )

        elapsed = time.perf_counter() - start
        times.append(elapsed)

    avg_seconds = sum(times) / len(times)
    avg_ms = avg_seconds * 1000

    # Một lần predict xử lý batch_size images
    batch_fps = 1.0 / avg_seconds
    image_fps = batch_size / avg_seconds

    print(f"Results returned : {len(results)}")
    print(f"AVG batch time   : {avg_ms:.2f} ms")
    print(f"Batches/sec      : {batch_fps:.2f}")
    print(f"Throughput       : {image_fps:.2f} images/sec")
    print(f"Latency/image*   : {avg_ms / batch_size:.2f} ms")

    # Ultralytics internal timing
    if results:
        speed = results[0].speed or {}

        print(
            f"Ultralytics      : "
            f"pre={speed.get('preprocess', 0):.2f} ms | "
            f"infer={speed.get('inference', 0):.2f} ms | "
            f"post={speed.get('postprocess', 0):.2f} ms"
        )


def main():
    print(f"Loading: {MODEL}")

    model = YOLO(MODEL)

    for batch_size in [1, 2, 4]:
        try:
            benchmark(model, batch_size)
        except Exception as e:
            print(f"\n❌ Batch {batch_size} FAILED")
            print(repr(e))


if __name__ == "__main__":
    main()