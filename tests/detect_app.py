"""
Script chạy thử detect-only runtime mới.

Ví dụ:
    python tests/detect_app.py --config configs/test.yaml --max-frames 200
    python tests/detect_app.py --config configs/test.yaml --no-show
"""

import argparse
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)


# -----------------------------------------------------------------------------
def parse_args():
    """Parse tham số CLI cho script chạy thử detection."""
    parser = argparse.ArgumentParser(description="Chạy detect-only runtime mới.")
    parser.add_argument(
        "--config",
        default="configs/test.yaml",
        help="Đường dẫn file YAML cấu hình.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Dừng sau N result để test nhanh. Mặc định chạy liên tục.",
    )

    show_group = parser.add_mutually_exclusive_group()
    show_group.add_argument(
        "--show",
        action="store_true",
        default=None,
        help="Bật cửa sổ OpenCV preview.",
    )
    show_group.add_argument(
        "--no-show",
        action="store_false",
        dest="show",
        help="Tắt cửa sổ OpenCV preview.",
    )

    return parser.parse_args()


# -----------------------------------------------------------------------------
def main() -> None:
    """Entry point cho script detect-only."""
    from src.app import run_detect_from_config

    args = parse_args()
    run_detect_from_config(
        args.config,
        max_frames=args.max_frames,
        show=args.show,
    )


# -----------------------------------------------------------------------------
if __name__ == "__main__":
    main()
