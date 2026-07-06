from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from pathlib import Path

from ultralytics import YOLO


SCRIPT_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = SCRIPT_DIR / "downloads"
OUTPUT_DIR = SCRIPT_DIR / "output" / "rknn"

TARGET = "rk3588"
MODELS = [
    "yolo26n.pt",
    "yolo26m.pt",
    "yolo26n-pose.pt",
    "yolo26m-pose.pt",
]
BATCHES = [1, 2]


def main() -> None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with pushd(DOWNLOAD_DIR):
        for model_name in MODELS:
            for batch in BATCHES:
                export_model(model_name, batch)


def export_model(model_name: str, batch: int) -> None:
    model_stem = Path(model_name).stem
    temp_dir = DOWNLOAD_DIR / f"{model_stem}_rknn_model"
    output_dir = OUTPUT_DIR / f"{model_stem}_b{batch}_{TARGET}_rknn_model"

    shutil.rmtree(temp_dir, ignore_errors=True)
    shutil.rmtree(output_dir, ignore_errors=True)

    print(f"Exporting {model_name} batch={batch} target={TARGET}")
    model = YOLO(model_name)
    exported_dir = Path(model.export(format="rknn", name=TARGET, batch=batch))

    shutil.move(str(exported_dir), output_dir)
    print(f"Saved: {output_dir}")


@contextmanager
def pushd(path: Path):
    old_cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)


if __name__ == "__main__":
    main()
