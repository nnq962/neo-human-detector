#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly VENV_DIR="${PROJECT_ROOT}/.venv"
readonly VENV_PYTHON="${VENV_DIR}/bin/python"
readonly OPENCV_WHEEL="${PROJECT_ROOT}/wheels/jp5.1.6-py38-aarch64/opencv_contrib_python-4.13.0.90-cp38-cp38-linux_aarch64.whl"
readonly TORCH_WHEEL="${PROJECT_ROOT}/wheels/jp5.1.6-py38-aarch64/torch-2.1.0a0+41361538.nv23.06-cp38-cp38-linux_aarch64.whl"
readonly TORCHVISION_WHEEL="${PROJECT_ROOT}/wheels/jp5.1.6-py38-aarch64/torchvision-0.16.1-cp38-cp38-linux_aarch64.whl"
readonly DEFAULT_CONFIG="${PROJECT_ROOT}/configs/default.yaml"
readonly EXAMPLE_CONFIG="${PROJECT_ROOT}/configs/default.example.yaml"
readonly FRONTEND_ENV="${PROJECT_ROOT}/frontend/.env"
readonly FRONTEND_ENV_EXAMPLE="${PROJECT_ROOT}/frontend/.env.example"

SKIP_SYSTEM_PACKAGES=false
SKIP_FRONTEND=false
SKIP_MODELS=false

usage() {
    printf '%s\n' \
        "Chuẩn bị NEO Human Detector trên Jetson JetPack 5.1.6." \
        "" \
        "Cách dùng:" \
        "  ./scripts/setup-jetson.sh [tùy chọn]" \
        "" \
        "Tùy chọn:" \
        "  --skip-system-packages  Không chạy apt-get." \
        "  --skip-frontend         Không chạy npm ci và npm run build." \
        "  --skip-models           Không kiểm tra hoặc tải model." \
        "  -h, --help              Hiển thị trợ giúp."
}

log() {
    printf '\n\033[1;34m[setup-jetson]\033[0m %s\n' "$*"
}

warn() {
    printf '\n\033[1;33m[setup-jetson] Cảnh báo:\033[0m %s\n' "$*" >&2
}

die() {
    printf '\n\033[1;31m[setup-jetson] Lỗi:\033[0m %s\n' "$*" >&2
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
    [[ "$(uname -m)" == "aarch64" ]] || die \
        "Cần máy aarch64; phát hiện $(uname -m)."
    [[ -r /etc/nv_tegra_release ]] || die \
        "Không tìm thấy /etc/nv_tegra_release; đây có thể không phải NVIDIA Jetson."

    local jetpack_version
    jetpack_version="$(
        dpkg-query -W -f='${Version}' nvidia-jetpack 2>/dev/null || true
    )"
    if [[ "${jetpack_version}" != 5.1.6* ]]; then
        die "Cần JetPack 5.1.6; phát hiện ${jetpack_version:-không xác định}."
    fi

    local l4t_version
    l4t_version="$(
        sed -n 's/^# R\([0-9]\+\) (release), REVISION: \([0-9.]\+\),.*$/\1.\2/p' \
            /etc/nv_tegra_release
    )"

    case "${l4t_version}" in
        35.6.4|35.6.5)
            ;;
        *)
            die "Cần L4T R35.6.4 hoặc R35.6.5; phát hiện R${l4t_version:-không xác định}."
            ;;
    esac

    [[ -r /etc/os-release ]] || die "Không xác định được Linux distribution."

    # shellcheck disable=SC1091
    source /etc/os-release
    [[ "${ID:-}" == "ubuntu" ]] || die \
        "Cần Ubuntu của JetPack; phát hiện ${ID:-unknown}."

    log "Nền tảng hợp lệ: JetPack ${jetpack_version}, L4T R${l4t_version} aarch64."
}

install_system_packages() {
    if [[ "${SKIP_SYSTEM_PACKAGES}" == true ]]; then
        log "Bỏ qua cài system package."
        return
    fi

    command -v apt-get >/dev/null 2>&1 || die "Không tìm thấy apt-get."

    local -a runtime_packages=(
        build-essential
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
        libglib2.0-0
        libgstreamer1.0-0
        libgtk-3-0
        libopenblas-dev
        libopenmpi-dev
        libwebpdemux2
        python3-dev
        python3-venv
    )

    log "Cài compiler, OpenBLAS, OpenMPI, FFmpeg và GStreamer."
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
    command -v uv >/dev/null 2>&1 || die \
        "Đã cài uv nhưng chưa tìm thấy executable."
}

prepare_python_environment() {
    [[ -x /usr/bin/python3 ]] || die "Không tìm thấy /usr/bin/python3."
    /usr/bin/python3 -c \
        'import sys; assert sys.version_info[:2] == (3, 8)' \
        || die "JetPack 5.1.6 cần system Python 3.8."

    if [[ -x "${VENV_PYTHON}" ]]; then
        "${VENV_PYTHON}" -c \
            'import sys; assert sys.version_info[:2] == (3, 8)' \
            || die ".venv hiện có không dùng Python 3.8."
        log "Giữ nguyên .venv Python 3.8 hiện có."
    elif [[ -e "${VENV_DIR}" ]]; then
        die ".venv tồn tại nhưng không phải virtual environment hợp lệ."
    else
        log "Tạo .venv riêng bằng system Python 3.8."
        uv venv --no-project --python /usr/bin/python3 "${VENV_DIR}"
    fi

    log "Cài dependency bootstrap cho trình đồng bộ artifact."
    uv pip install --no-config --python "${VENV_PYTHON}" \
        "gdown==5.2.2" \
        "numpy==1.24.4" \
        "pyyaml==6.0.3"
}

sync_bootstrap_artifacts() {
    log "Kiểm tra và tải wheel cho JetPack 5.1.6."
    (
        cd "${PROJECT_ROOT}"
        "${VENV_PYTHON}" scripts/sync-artifacts.py \
            --platform jetson-aarch64
    )
}

check_local_artifacts() {
    local artifact
    for artifact in "${OPENCV_WHEEL}" "${TORCH_WHEEL}" "${TORCHVISION_WHEEL}"; do
        [[ -f "${artifact}" ]] || die "Thiếu wheel: ${artifact}"
    done
    [[ -f "${EXAMPLE_CONFIG}" ]] || die "Thiếu config mẫu: ${EXAMPLE_CONFIG}"

    log "Đã có đủ OpenCV, torch và torchvision wheel CPython 3.8 aarch64."
}

sync_python_environment() {
    log "Đồng bộ dependency Jetson bằng uv.lock với Python 3.8."
    (
        cd "${PROJECT_ROOT}"
        UV_LINK_MODE=copy uv sync --locked --python "${VENV_PYTHON}" --no-dev
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

sync_models() {
    if [[ "${SKIP_MODELS}" == true ]]; then
        log "Bỏ qua đồng bộ model."
        return
    fi

    log "Kiểm tra và tải model dành cho Jetson aarch64."
    (
        cd "${PROJECT_ROOT}"
        "${VENV_PYTHON}" scripts/sync-models.py --platform jetson-aarch64
    )
}

verify_installation() {
    log "Kiểm tra Python, CUDA, OpenCV, GStreamer và API."
    (
        cd "${PROJECT_ROOT}"
        MPLCONFIGDIR="${PROJECT_ROOT}/tmp/matplotlib" "${VENV_PYTHON}" -c \
            'import cv2, torch, torchvision, ultralytics; assert torch.cuda.is_available(), "PyTorch không truy cập được CUDA"; assert "GStreamer:                   YES" in cv2.getBuildInformation(), "OpenCV chưa bật GStreamer"; import api.server; print(f"Python: 3.8 | torch: {torch.__version__} | torchvision: {torchvision.__version__} | CUDA: {torch.version.cuda} | OpenCV: {cv2.__version__} | ultralytics: {ultralytics.__version__}")'
        "${VENV_PYTHON}" -c \
            'import yaml; data = yaml.safe_load(open("configs/default.yaml", encoding="utf-8")); assert isinstance(data, dict); print("configs/default.yaml: YAML hợp lệ")'
    )
}

report_optional_requirements() {
    local current_user
    current_user="$(id -un)"
    if ! id -nG "${current_user}" | tr ' ' '\n' | grep -qx dialout; then
        warn "User ${current_user} chưa thuộc group dialout. Chạy: sudo usermod -aG dialout ${current_user}, sau đó đăng xuất/đăng nhập lại."
    fi

    if curl -fsS --max-time 2 \
        "http://127.0.0.1:9997/v3/config/global/get" >/dev/null 2>&1; then
        log "MediaMTX API đang hoạt động tại 127.0.0.1:9997."
    else
        warn "Chưa kết nối được MediaMTX API; camera WebRTC có thể chưa hoạt động."
    fi
}

main() {
    parse_arguments "$@"
    cd "${PROJECT_ROOT}"

    check_platform
    install_system_packages
    install_uv_if_needed
    prepare_python_environment
    sync_bootstrap_artifacts
    check_local_artifacts
    sync_python_environment
    prepare_config
    sync_models
    build_frontend
    verify_installation
    report_optional_requirements

    log "Setup Jetson hoàn tất. Chạy ứng dụng bằng: ./scripts/run.sh"
}

main "$@"
