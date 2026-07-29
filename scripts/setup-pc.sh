#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly OPENCV_WHEEL="${PROJECT_ROOT}/wheels/pc-x86_64/opencv_python-4.13.0.92-cp310-cp310-linux_x86_64.whl"
readonly OPENCV_WHEEL_SHA256="79323abd4caf34263538384b2af954533a951215f6fb22150fac0f584e3b6a81"
readonly DEFAULT_CONFIG="${PROJECT_ROOT}/configs/default.yaml"
readonly EXAMPLE_CONFIG="${PROJECT_ROOT}/configs/default.example.yaml"
readonly FRONTEND_ENV="${PROJECT_ROOT}/frontend/.env"
readonly FRONTEND_ENV_EXAMPLE="${PROJECT_ROOT}/frontend/.env.example"
readonly SUPERVISOR_TEMPLATE="${PROJECT_ROOT}/deploy/supervisor/neo-human-detector.conf.template"
readonly SUPERVISOR_CONFIG="/etc/supervisor/conf.d/neo-human-detector.conf"

SKIP_SYSTEM_PACKAGES=false
SKIP_FRONTEND=false
SKIP_MODELS=false
WITH_SUPERVISOR=false

usage() {
    printf '%s\n' \
        "Chuẩn bị môi trường chạy NEO Human Detector trên PC x86_64." \
        "" \
        "Cách dùng:" \
        "  ./scripts/setup-pc.sh [tùy chọn]" \
        "" \
        "Tùy chọn:" \
        "  --skip-system-packages  Không chạy apt-get." \
        "  --skip-frontend         Không chạy npm ci và npm run build." \
        "  --skip-models           Không kiểm tra hoặc tải model." \
        "  --with-supervisor       Cài và chạy ứng dụng bằng Supervisor." \
        "  -h, --help              Hiển thị trợ giúp."
}

log() {
    printf '\n\033[1;34m[setup-pc]\033[0m %s\n' "$*"
}

warn() {
    printf '\n\033[1;33m[setup-pc] Cảnh báo:\033[0m %s\n' "$*" >&2
}

die() {
    printf '\n\033[1;31m[setup-pc] Lỗi:\033[0m %s\n' "$*" >&2
    exit 1
}

run_as_root() {
    if [[ "$(id -u)" -eq 0 ]]; then
        "$@"
        return
    fi

    command -v sudo >/dev/null 2>&1 || die "Cần sudo để cài system package."
    sudo "$@"
}

parse_arguments() {
    while (($# > 0)); do
        case "$1" in
            --skip-system-packages)
                SKIP_SYSTEM_PACKAGES=true
                ;;
            --skip-frontend)
                SKIP_FRONTEND=true
                ;;
            --skip-models)
                SKIP_MODELS=true
                ;;
            --with-supervisor)
                WITH_SUPERVISOR=true
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

check_platform() {
    [[ "$(uname -s)" == "Linux" ]] || die "Script này chỉ hỗ trợ Linux."
    [[ "$(uname -m)" == "x86_64" ]] || die "Cần máy x86_64; phát hiện $(uname -m)."

    if [[ ! -r /etc/os-release ]]; then
        die "Không xác định được Linux distribution."
    fi

    # shellcheck disable=SC1091
    source /etc/os-release
    if [[ "${ID:-}" != "ubuntu" && "${ID_LIKE:-}" != *"debian"* ]]; then
        die "Hiện script chỉ hỗ trợ Ubuntu/Debian; phát hiện ${ID:-unknown}."
    fi

    log "Nền tảng hợp lệ: ${PRETTY_NAME:-Linux} x86_64."
}

install_system_packages() {
    if [[ "${SKIP_SYSTEM_PACKAGES}" == true ]]; then
        log "Bỏ qua cài system package."
        return
    fi

    command -v apt-get >/dev/null 2>&1 || die "Không tìm thấy apt-get."

    local -a runtime_packages=(
        ca-certificates
        curl
        ffmpeg
        gstreamer1.0-libav
        gstreamer1.0-plugins-bad
        gstreamer1.0-plugins-base
        gstreamer1.0-plugins-good
        gstreamer1.0-plugins-ugly
        gstreamer1.0-tools
        libgl1
        libgstreamer1.0-0
        libwebpdemux2
    )

    # Ubuntu 24.04 đổi một số package runtime sang hậu tố t64.
    if [[ "${VERSION_ID:-}" == "24.04" ]]; then
        runtime_packages+=(libglib2.0-0t64 libgtk-3-0t64)
    else
        runtime_packages+=(libglib2.0-0 libgtk-3-0)
    fi
    if [[ "${WITH_SUPERVISOR}" == true ]]; then
        runtime_packages+=(supervisor)
    fi

    log "Cài FFmpeg, GStreamer và thư viện runtime OpenCV."
    run_as_root apt-get update
    run_as_root env DEBIAN_FRONTEND=noninteractive \
        apt-get install -y --no-install-recommends "${runtime_packages[@]}"
}

install_uv_if_needed() {
    if command -v uv >/dev/null 2>&1; then
        log "Đã có $(uv --version)."
        return
    fi

    command -v curl >/dev/null 2>&1 || die "Cần curl để cài uv."

    local installer
    installer="$(mktemp)"
    log "Cài uv bằng installer chính thức."
    curl -LsSf https://astral.sh/uv/install.sh -o "${installer}"
    sh "${installer}"
    rm -f "${installer}"

    export PATH="${HOME}/.local/bin:${PATH}"
    command -v uv >/dev/null 2>&1 || die "Đã cài uv nhưng chưa tìm thấy executable."
}

check_node() {
    command -v node >/dev/null 2>&1 || die \
        "Chưa có Node.js. Hãy cài Node.js >=20.19 hoặc >=22.12 rồi chạy lại."
    command -v npm >/dev/null 2>&1 || die "Không tìm thấy npm."

    if ! node -e '
        const [major, minor] = process.versions.node.split(".").map(Number);
        const valid = (major === 20 && minor >= 19)
            || (major === 22 && minor >= 12)
            || major > 22;
        process.exit(valid ? 0 : 1);
    '; then
        die "Node.js $(node --version) không phù hợp; cần >=20.19 hoặc >=22.12."
    fi

    log "Node.js $(node --version) và npm $(npm --version) hợp lệ."
}

check_local_artifacts() {
    [[ -f "${OPENCV_WHEEL}" ]] || die \
        "Thiếu OpenCV wheel: ${OPENCV_WHEEL}"
    [[ -f "${EXAMPLE_CONFIG}" ]] || die \
        "Thiếu config mẫu: ${EXAMPLE_CONFIG}"

    log "Đã tìm thấy OpenCV wheel dành cho CPython 3.10 x86_64."
}

sync_bootstrap_artifacts() {
    if [[ -f "${OPENCV_WHEEL}" ]]; then
        local actual_sha256
        actual_sha256="$(sha256sum "${OPENCV_WHEEL}" | cut -d ' ' -f 1)"
        if [[ "${actual_sha256}" == "${OPENCV_WHEEL_SHA256}" ]]; then
            log "OpenCV wheel đã tồn tại và đúng checksum."
            return
        fi
    fi

    log "Kiểm tra và tải OpenCV wheel dành cho PC x86_64."
    (
        cd "${PROJECT_ROOT}"
        uv run \
            --no-project \
            --with 'gdown>=5.2.2' \
            --with 'pyyaml>=6.0.3' \
            python scripts/sync-artifacts.py --platform pc-x86_64
    )
}

prepare_config() {
    if [[ -e "${DEFAULT_CONFIG}" ]]; then
        log "Giữ nguyên configs/default.yaml hiện có."
        return
    fi

    cp "${EXAMPLE_CONFIG}" "${DEFAULT_CONFIG}"
    log "Đã tạo configs/default.yaml từ file example."
}

prepare_frontend_env() {
    [[ -f "${FRONTEND_ENV_EXAMPLE}" ]] || die \
        "Thiếu frontend env mẫu: ${FRONTEND_ENV_EXAMPLE}"

    if [[ ! -e "${FRONTEND_ENV}" ]]; then
        if [[ -n "${VITE_API_BASE_URL:-}" && -n "${VITE_CONFIG_PASSWORD:-}" ]]; then
            (
                umask 077
                printf 'VITE_API_BASE_URL=%s\nVITE_CONFIG_PASSWORD=%s\n' \
                    "${VITE_API_BASE_URL}" \
                    "${VITE_CONFIG_PASSWORD}" >"${FRONTEND_ENV}"
            )
            log "Đã tạo frontend/.env từ biến môi trường của terminal."
        else
            cp "${FRONTEND_ENV_EXAMPLE}" "${FRONTEND_ENV}"
            die "Đã tạo frontend/.env. Hãy chỉnh API URL và mật khẩu, sau đó chạy lại setup."
        fi
    else
        log "Giữ nguyên frontend/.env hiện có."
    fi

    local api_base_url
    local config_password
    api_base_url="$(sed -n 's/^VITE_API_BASE_URL=//p' "${FRONTEND_ENV}" | tail -n 1)"
    config_password="$(sed -n 's/^VITE_CONFIG_PASSWORD=//p' "${FRONTEND_ENV}" | tail -n 1)"

    [[ -n "${api_base_url}" ]] || die "frontend/.env thiếu VITE_API_BASE_URL."
    [[ "${api_base_url}" != *"["* ]] || die \
        "VITE_API_BASE_URL trong frontend/.env vẫn là placeholder."
    [[ -n "${config_password}" && "${config_password}" != "change-me" ]] || die \
        "Hãy đặt VITE_CONFIG_PASSWORD trong frontend/.env trước khi build."

    log "Frontend env hợp lệ với API: ${api_base_url}"
}

sync_python_environment() {
    log "Chuẩn bị Python 3.10 và đồng bộ dependency từ uv.lock."
    (
        cd "${PROJECT_ROOT}"
        if uv python find 3.10 >/dev/null 2>&1; then
            log "Python 3.10 đã sẵn sàng."
        else
            uv python install 3.10
        fi
        UV_LINK_MODE=copy uv sync --locked
    )
}

sync_models() {
    if [[ "${SKIP_MODELS}" == true ]]; then
        log "Bỏ qua đồng bộ model."
        return
    fi

    log "Kiểm tra và tải model dành cho PC x86_64."
    (
        cd "${PROJECT_ROOT}"
        uv run --locked python scripts/sync-models.py --platform pc-x86_64
    )
}

build_frontend() {
    if [[ "${SKIP_FRONTEND}" == true ]]; then
        log "Bỏ qua frontend build."
        return
    fi

    prepare_frontend_env
    check_node
    log "Cài dependency và build frontend."
    (
        cd "${PROJECT_ROOT}/frontend"
        npm ci
        npm run build
    )
}

verify_installation() {
    log "Kiểm tra OpenCV, GStreamer và config."
    (
        cd "${PROJECT_ROOT}"
        uv run --locked python -c \
            'import cv2; info = cv2.getBuildInformation(); assert "GStreamer:                   YES" in info, "OpenCV chưa bật GStreamer"; print(f"OpenCV {cv2.__version__}: GStreamer YES")'
        uv run --locked python -c \
            'import yaml; yaml.safe_load(open("configs/default.yaml", encoding="utf-8")); print("configs/default.yaml: YAML hợp lệ")'
    )
}

configure_supervisor() {
    if [[ "${WITH_SUPERVISOR}" != true ]]; then
        return
    fi

    command -v supervisorctl >/dev/null 2>&1 || die \
        "Không tìm thấy supervisorctl. Bỏ --skip-system-packages hoặc cài supervisor."
    [[ -f "${SUPERVISOR_TEMPLATE}" ]] || die \
        "Thiếu Supervisor template: ${SUPERVISOR_TEMPLATE}"

    local run_user
    local user_home
    local uv_bin
    local uv_dir
    local rendered_config
    run_user="${SUDO_USER:-$(id -un)}"
    user_home="$(getent passwd "${run_user}" | cut -d: -f6)"
    uv_bin="$(command -v uv)"
    uv_dir="$(dirname -- "${uv_bin}")"
    [[ -n "${user_home}" ]] || die "Không xác định được home của user ${run_user}."

    mkdir -p "${PROJECT_ROOT}/logs"
    rendered_config="$(mktemp)"
    sed \
        -e "s|__PROJECT_ROOT__|${PROJECT_ROOT}|g" \
        -e "s|__RUN_USER__|${run_user}|g" \
        -e "s|__USER_HOME__|${user_home}|g" \
        -e "s|__UV_DIR__|${uv_dir}|g" \
        "${SUPERVISOR_TEMPLATE}" >"${rendered_config}"

    log "Cài Supervisor config cho user ${run_user}."
    run_as_root install -m 0644 "${rendered_config}" "${SUPERVISOR_CONFIG}"
    rm -f "${rendered_config}"

    if command -v systemctl >/dev/null 2>&1; then
        run_as_root systemctl enable --now supervisor
    fi
    run_as_root supervisorctl reread
    run_as_root supervisorctl update

    log "Supervisor đã quản lý program neo-human-detector."
}

report_optional_requirements() {
    local detection_count
    detection_count="$(
        find "${PROJECT_ROOT}/weights" -type f \
            \( -name '*.pt' -o -name '*.onnx' -o -name '*.engine' -o -name '*.rknn' \) \
            2>/dev/null | wc -l
    )"

    if ((detection_count == 0)); then
        warn "Chưa tìm thấy detection model trong weights/."
    else
        log "Tìm thấy ${detection_count} detection model trong weights/."
    fi

    if curl -fsS --max-time 2 \
        "http://127.0.0.1:9997/v3/config/global/get" >/dev/null 2>&1; then
        log "MediaMTX API đang hoạt động tại 127.0.0.1:9997."
    elif command -v docker >/dev/null 2>&1 \
        && docker ps --format '{{.Image}} {{.Names}}' 2>/dev/null \
            | grep -qi 'mediamtx'; then
        log "Tìm thấy MediaMTX container đang chạy."
    elif command -v mediamtx >/dev/null 2>&1; then
        log "Đã tìm thấy MediaMTX executable trên máy host."
    else
        warn "Chưa kết nối được MediaMTX API và không tìm thấy MediaMTX đang chạy."
    fi

    local current_user
    current_user="$(id -un)"
    if ! id -nG "${current_user}" | tr ' ' '\n' | grep -qx dialout; then
        warn "User ${current_user} chưa thuộc group dialout. Chạy: sudo usermod -aG dialout ${current_user}, sau đó đăng xuất/đăng nhập lại."
    fi
}

main() {
    parse_arguments "$@"
    cd "${PROJECT_ROOT}"

    check_platform
    install_system_packages
    install_uv_if_needed
    sync_bootstrap_artifacts
    check_local_artifacts
    prepare_config
    sync_python_environment
    sync_models
    build_frontend
    verify_installation
    configure_supervisor
    report_optional_requirements

    if [[ "${WITH_SUPERVISOR}" == true ]]; then
        log "Setup PC hoàn tất. Kiểm tra app bằng: sudo supervisorctl status neo-human-detector"
    else
        log "Setup PC hoàn tất. Chạy ứng dụng bằng: ./scripts/run.sh"
    fi
}

main "$@"
