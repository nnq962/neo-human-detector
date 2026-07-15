from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException
from api.routes import auto_start, camera, detection, mediamtx, reid, runtime, uart, websocket, zone_state_machine
from api.routes.responses import error_response


STANDARD_RESPONSE_PREFIXES = (
    "/api/cameras",
    "/api/auto-start",
    "/api/detection",
    "/api/mediamtx",
    "/api/reid",
    "/api/runtime",
    "/api/uart",
    "/api/zone-state-machine",
)


def _uses_standard_api_response(path: str) -> bool:
    return any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in STANDARD_RESPONSE_PREFIXES
    )


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
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


def run_startup_tasks() -> None:
    from api.services.config_store import get_config_data
    from api.services.load_cameras import sync_camera_paths, wait_for_mediamtx
    from api.services.runtime import DEFAULT_CONFIG_PATH, start_runtime
    from api.models.runtime import RuntimeCommandRequest
    from utils import LOGGER

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

    if cfg.get("auto_start") is True:
        try:
            start_runtime(RuntimeCommandRequest(config_path=DEFAULT_CONFIG_PATH, preview=False))
            LOGGER.info("Runtime auto-start requested from config.")
        except Exception as e:
            LOGGER.error(f"Failed to auto-start runtime: {e}")


def run_shutdown_tasks() -> None:
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_startup_tasks()
    try:
        yield
    finally:
        run_shutdown_tasks()


OPENAPI_TAGS = [
    {"name": "Auto Start", "description": "Runtime auto-start configuration."},
    {"name": "Detection", "description": "Detection model configuration."},
    {"name": "MediaMTX", "description": "MediaMTX integration utilities."},
    {"name": "Cameras", "description": "Camera and zone configuration."},
    {"name": "Zone State Machine", "description": "Zone state timing configuration."},
    {"name": "ReID", "description": "Re-identification configuration."},
    {"name": "Runtime", "description": "Application runtime lifecycle."},
    {"name": "UART", "description": "UART serial configuration."},
]


app = FastAPI(lifespan=lifespan, openapi_tags=OPENAPI_TAGS)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if _uses_standard_api_response(request.url.path):
        return error_response(exc.status_code, str(exc.detail))

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    if _uses_standard_api_response(request.url.path):
        return error_response(422, "Validation error.", exc.errors())

    return JSONResponse(status_code=422, content={"detail": exc.errors()})

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cho phép tất cả các domain. Có thể thay bằng list cụ thể, vd: ["http://localhost:3000"]
    allow_credentials=True, # Cho phép gửi cookie, thông tin xác thực
    allow_methods=["*"],  # Cho phép tất cả các method HTTP (GET, POST, PUT, DELETE, OPTIONS...)
    allow_headers=["*"],  # Cho phép tất cả các header
)

# ────────────────────────────────────────────────────────────────
app.include_router(auto_start.router, prefix="/api/auto-start", tags=["Auto Start"])
app.include_router(detection.router, prefix="/api/detection", tags=["Detection"])
app.include_router(mediamtx.router, prefix="/api/mediamtx", tags=["MediaMTX"])
app.include_router(camera.router, prefix="/api/cameras", tags=["Cameras"])
app.include_router(zone_state_machine.router, prefix="/api/zone-state-machine", tags=["Zone State Machine"],)
app.include_router(reid.router, prefix="/api/reid", tags=["ReID"])
app.include_router(runtime.router, prefix="/api/runtime", tags=["Runtime"])
app.include_router(uart.router, prefix="/api/uart", tags=["UART"])
app.include_router(websocket.router)

# ────────────────────────────────────────────────────────────────
# Mount frontend build
app.mount("/", SPAStaticFiles(directory="frontend/dist", html=True), name="frontend")
