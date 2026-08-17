from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException
from api.routes import (
    auth,
    camera,
    detection,
    mediamtx,
    models,
    public,
    reid,
    runtime,
    uart,
    websocket,
    zone_state_machine,
)
from api.routes.responses import error_response
from api.services.auth import auth_service, is_origin_allowed, load_auth_settings


STANDARD_RESPONSE_PREFIXES = (
    "/api/public",
    "/api/cameras",
    "/api/detection",
    "/api/mediamtx",
    "/api/models",
    "/api/reid",
    "/api/runtime",
    "/api/uart",
    "/api/zone-state-machine",
)
PUBLIC_API_PREFIXES = ("/api/auth", "/api/public")
SAFE_HTTP_METHODS = {"GET", "HEAD", "OPTIONS"}


# ─────────────────────────────────────────────────────────────────────────────
def _uses_standard_api_response(path: str) -> bool:
    """Kiểm tra endpoint có dùng envelope response chuẩn của dự án."""
    return any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in STANDARD_RESPONSE_PREFIXES
    )


# ─────────────────────────────────────────────────────────────────────────────
def _is_public_api_path(path: str) -> bool:
    """Kiểm tra path thuộc bề mặt API không yêu cầu đăng nhập."""
    return any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in PUBLIC_API_PREFIXES
    )


class SPAStaticFiles(StaticFiles):
    """Phục vụ frontend SPA và fallback route về ``index.html``."""

    async def get_response(self, path: str, scope):
        """Trả asset tĩnh hoặc index cho một route điều hướng phía client."""
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise

            method = scope.get("method")
            headers = Headers(scope=scope)
            accept = headers.get("accept", "")
            wants_html = "text/html" in accept or "*/*" in accept

            if method not in ("GET", "HEAD") or not wants_html:
                raise

            return await super().get_response("index.html", scope)


# ─────────────────────────────────────────────────────────────────────────────
def run_startup_tasks() -> None:
    """Khởi tạo catalog model và các dịch vụ phụ trợ khi API bắt đầu."""
    from api.services.config_store import get_config_data
    from api.services.load_cameras import sync_camera_paths, wait_for_mediamtx
    from api.services.runtime import DEFAULT_CONFIG_PATH, start_runtime
    from api.models.runtime import RuntimeCommandRequest
    from utils import LOGGER
    from src.model_catalog import list_models

    models = list_models()
    detection_count = sum(model.kind == "detection" for model in models)
    reid_count = sum(model.kind == "reid" for model in models)
    LOGGER.info(
        "Model catalog scan completed: %d detection, %d ReID.",
        detection_count,
        reid_count,
    )

    try:
        cfg = get_config_data()
    except Exception as e:
        LOGGER.error(f"Failed to load config on startup: {e}")
        return

    try:
        wait_for_mediamtx()
        result = sync_camera_paths(cfg)
        LOGGER.info(
            "MediaMTX camera sync completed: "
            f"{result['synced']} synced, {result['failed']} failed, {result['skipped']} skipped."
        )
    except Exception as e:
        LOGGER.error(f"Failed to sync MediaMTX camera paths: {e}")

    try:
        from api.services.manual_robot_task import manual_robot_task_service
        from api.services.robot_heartbeat import robot_heartbeat_service
        from uart_v2.uart_manager import uart_manager_v2

        manual_robot_task_service.register_uart_handlers()
        robot_heartbeat_service.register_uart_handler(uart_manager_v2)
        if not uart_manager_v2.connect():
            LOGGER.error("Failed to initialize UART V2: %s", uart_manager_v2.last_error)
    except Exception as e:
        LOGGER.error(f"Failed to initialize UART V2: {e}")

    if (cfg.get("runtime") or {}).get("auto_start") is True:
        try:
            start_runtime(RuntimeCommandRequest(config_path=DEFAULT_CONFIG_PATH, preview=False))
            LOGGER.info("Runtime auto-start requested from config.")
        except Exception as e:
            LOGGER.error(f"Failed to auto-start runtime: {e}")


# ─────────────────────────────────────────────────────────────────────────────
def run_shutdown_tasks() -> None:
    """Dừng runtime và đóng các dịch vụ UART khi API kết thúc."""
    from utils import LOGGER

    try:
        from api.services.runtime import stop_runtime

        stop_runtime()
    except Exception as e:
        LOGGER.error(f"Failed to stop Runtime: {e}")

    try:
        from api.services.manual_robot_task import manual_robot_task_service
        from api.services.robot_heartbeat import robot_heartbeat_service
        from uart_v2.uart_manager import uart_manager_v2

        manual_robot_task_service.close()
        robot_heartbeat_service.close()
        uart_manager_v2.close()
    except Exception as e:
        LOGGER.error(f"Failed to close UART V2: {e}")


# ─────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Quản lý startup và shutdown trong vòng đời ứng dụng FastAPI."""
    run_startup_tasks()
    try:
        yield
    finally:
        run_shutdown_tasks()


OPENAPI_TAGS = [
    {"name": "Detection", "description": "Detection model configuration."},
    {"name": "MediaMTX", "description": "MediaMTX integration utilities."},
    {"name": "Models", "description": "Available AI model catalog."},
    {"name": "Cameras", "description": "Camera and zone configuration."},
    {"name": "Zone State Machine", "description": "Zone state timing configuration."},
    {"name": "ReID", "description": "Re-identification configuration."},
    {"name": "Runtime", "description": "Application runtime lifecycle."},
    {"name": "UART", "description": "UART serial configuration."},
]


app = FastAPI(lifespan=lifespan, openapi_tags=OPENAPI_TAGS)


# ─────────────────────────────────────────────────────────────────────────────
@app.middleware("http")
async def require_authenticated_api(request: Request, call_next):
    """Chặn API riêng tư nếu request không có session hợp lệ."""
    path = request.url.path
    if (
        request.method == "OPTIONS"
        or not path.startswith("/api/")
        or _is_public_api_path(path)
    ):
        return await call_next(request)

    settings = load_auth_settings()
    if not settings.enabled:
        return await call_next(request)
    if not settings.password_hash:
        return error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Xác thực web chưa được cấu hình.",
        )

    token = request.cookies.get(auth.SESSION_COOKIE_NAME)
    if not auth_service.is_session_valid(token):
        return error_response(
            status.HTTP_401_UNAUTHORIZED,
            "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
        )

    if request.method not in SAFE_HTTP_METHODS and not is_origin_allowed(
        request.headers.get("origin"),
        scheme=request.url.scheme,
        host=request.headers.get("host", request.url.netloc),
    ):
        return error_response(
            status.HTTP_403_FORBIDDEN,
            "Origin không được phép thực hiện thao tác này.",
        )

    return await call_next(request)


# ─────────────────────────────────────────────────────────────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Chuẩn hóa lỗi HTTP theo loại endpoint đang được gọi."""
    if _uses_standard_api_response(request.url.path):
        return error_response(exc.status_code, str(exc.detail))

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


# ─────────────────────────────────────────────────────────────────────────────
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Chuẩn hóa lỗi validation theo envelope response của API."""
    if _uses_standard_api_response(request.url.path):
        return error_response(422, "Validation error.", exc.errors())

    return JSONResponse(status_code=422, content={"detail": exc.errors()})

try:
    configured_origins = list(load_auth_settings().allowed_origins)
except Exception:
    configured_origins = []

if configured_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configured_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

# ─────────────────────────────────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(public.router, prefix="/api/public", tags=["Public"])
app.include_router(detection.router, prefix="/api/detection", tags=["Detection"])
app.include_router(mediamtx.router, prefix="/api/mediamtx", tags=["MediaMTX"])
app.include_router(models.router, prefix="/api/models", tags=["Models"])
app.include_router(camera.router, prefix="/api/cameras", tags=["Cameras"])
app.include_router(zone_state_machine.router, prefix="/api/zone-state-machine", tags=["Zone State Machine"],)
app.include_router(reid.router, prefix="/api/reid", tags=["ReID"])
app.include_router(runtime.router, prefix="/api/runtime", tags=["Runtime"])
app.include_router(uart.router, prefix="/api/uart", tags=["UART"])
app.include_router(websocket.router)

# ─────────────────────────────────────────────────────────────────────────────
# Mount frontend build
app.mount("/", SPAStaticFiles(directory="frontend/dist", html=True), name="frontend")
