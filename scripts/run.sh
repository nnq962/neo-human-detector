#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly DEFAULT_CONFIG="${PROJECT_ROOT}/configs/default.yaml"
readonly FRONTEND_DIST="${PROJECT_ROOT}/frontend/dist"
readonly OPENCV_WHEEL="${PROJECT_ROOT}/wheels/pc-x86_64/opencv_python-4.13.0.92-cp310-cp310-linux_x86_64.whl"

SKIP_MODEL_SYNC=false
CHECK_ONLY=false

usage() {
    printf '%s\n' \
        "Kiểm tra điều kiện cần thiết và chạy NEO Human Detector." \
        "" \
        "Cách dùng:" \
        "  ./scripts/run.sh [tùy chọn]" \
        "" \
        "Tùy chọn:" \
        "  --skip-model-sync  Không kiểm tra hoặc tải model trước khi chạy." \
        "  --check            Chỉ kiểm tra, không khởi động ứng dụng." \
        "  -h, --help         Hiển thị trợ giúp."
}

log() {
    printf '\n\033[1;34m[run]\033[0m %s\n' "$*"
}

warn() {
    printf '\n\033[1;33m[run] Cảnh báo:\033[0m %s\n' "$*" >&2
}

die() {
    printf '\n\033[1;31m[run] Lỗi:\033[0m %s\n' "$*" >&2
    exit 1
}

parse_arguments() {
    while (($# > 0)); do
        case "$1" in
            --skip-model-sync)
                SKIP_MODEL_SYNC=true
                ;;
            --check)
                CHECK_ONLY=true
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                die "Tùy chọn không hợp lệ: $1"
                ;;
        esac
        shift
    done
}

check_required_files() {
    command -v uv >/dev/null 2>&1 || die \
        "Không tìm thấy uv. Hãy chạy ./scripts/setup-pc.sh trước."
    [[ -f "${DEFAULT_CONFIG}" ]] || die \
        "Thiếu configs/default.yaml. Hãy chạy ./scripts/setup-pc.sh trước."
    [[ -r "${DEFAULT_CONFIG}" ]] || die \
        "Không có quyền đọc configs/default.yaml."
    [[ -w "${DEFAULT_CONFIG}" ]] || die \
        "Không có quyền ghi configs/default.yaml; giao diện sẽ không lưu được config."
    [[ -w "$(dirname -- "${DEFAULT_CONFIG}")" ]] || die \
        "Không có quyền ghi thư mục configs/."
    [[ -f "${FRONTEND_DIST}/index.html" ]] || die \
        "Frontend chưa được build. Hãy chạy ./scripts/setup-pc.sh trước."
    [[ -f "${OPENCV_WHEEL}" ]] || die \
        "Thiếu OpenCV wheel. Hãy chạy ./scripts/setup-pc.sh trước."
}

validate_config() {
    log "Kiểm tra configs/default.yaml."
    (
        cd "${PROJECT_ROOT}"
        uv run --locked python -c \
            'import yaml; data = yaml.safe_load(open("configs/default.yaml", encoding="utf-8")); assert isinstance(data, dict), "Config root phải là mapping YAML."'
    )
}

sync_models() {
    if [[ "${SKIP_MODEL_SYNC}" == true ]]; then
        log "Bỏ qua đồng bộ model."
        return
    fi

    log "Kiểm tra và tải model còn thiếu."
    (
        cd "${PROJECT_ROOT}"
        uv run --locked python scripts/sync-models.py
    )
}

check_mediamtx() {
    if curl -fsS --max-time 2 \
        "http://127.0.0.1:9997/v3/config/global/get" >/dev/null 2>&1; then
        log "MediaMTX API đang hoạt động."
        return
    fi

    if command -v docker >/dev/null 2>&1 \
        && docker ps --format '{{.Image}} {{.Names}}' 2>/dev/null \
            | grep -qi 'mediamtx'; then
        warn "MediaMTX container đang chạy nhưng API port 9997 chưa phản hồi."
        return
    fi

    warn "Không kết nối được MediaMTX; camera WebRTC có thể không hoạt động."
}

main() {
    parse_arguments "$@"
    cd "${PROJECT_ROOT}"

    check_required_files
    validate_config
    sync_models
    check_mediamtx

    if [[ "${CHECK_ONLY}" == true ]]; then
        log "Kiểm tra hoàn tất, ứng dụng chưa được khởi động."
        return
    fi

    log "Khởi động ứng dụng tại http://0.0.0.0:9721"
    exec uv run --locked python main.py
}

main "$@"
