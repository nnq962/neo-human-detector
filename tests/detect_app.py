"""
Script chạy thử detect + zone runtime mới.

Ví dụ:
    python tests/detect_app.py --config configs/test.yaml --max-frames 200
    python tests/detect_app.py --config configs/test.yaml --no-show
    python tests/detect_app.py --config configs/test.yaml --track --show
"""

import argparse
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)


# ─────────────────────────────────────────────────────────────────────────────
def parse_args():
    """Parse tham số CLI cho script chạy thử detection."""
    parser = argparse.ArgumentParser(description="Chạy detect + zone runtime mới.")
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
    parser.add_argument(
        "--track",
        action="store_true",
        help="Bật ByteTrack built-in của Ultralytics để test track_id.",
    )
    parser.add_argument(
        "--tracker",
        default="bytetrack.yaml",
        help="Tracker config của Ultralytics, mặc định bytetrack.yaml.",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Tắt persist tracker state giữa các frame.",
    )

    reid_group = parser.add_mutually_exclusive_group()
    reid_group.add_argument(
        "--reid",
        action="store_true",
        default=None,
        help="Bật ReID stage. Runtime sẽ tự dùng ByteTrack để lấy track_id.",
    )
    reid_group.add_argument(
        "--no-reid",
        action="store_false",
        dest="reid",
        help="Tắt ReID stage, kể cả khi YAML đang bật.",
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


# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    """Entry point cho script detect + zone."""
    args = parse_args()

    from src.app import run_detect_from_config

    run_detect_from_config(
        args.config,
        max_frames=args.max_frames,
        show=args.show,
        use_tracking=args.track,
        tracker=args.tracker,
        persist=not args.no_persist,
        enable_reid=args.reid,
    )


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
