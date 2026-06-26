from fastapi import APIRouter

from api.models.response import ApiResponse
from api.models.uart import UartConfig, UartConfigUpdate, UartSendStringRequest
from api.routes.responses import error_from_exception, ok
from api.services import uart as uart_service


router = APIRouter()


@router.get("", response_model=ApiResponse)
def get_uart_config():
    try:
        return ok("UART config loaded successfully.", uart_service.get_uart_config())
    except Exception as error:
        return error_from_exception(error)


@router.get("/status", response_model=ApiResponse)
def get_uart_status():
    try:
        return ok("UART status loaded successfully.", uart_service.get_uart_status())
    except Exception as error:
        return error_from_exception(error)


@router.post("/send-string", response_model=ApiResponse)
def send_uart_string(request: UartSendStringRequest):
    try:
        return ok(
            "UART command sent successfully.",
            uart_service.send_uart_string(request.command),
        )
    except Exception as error:
        return error_from_exception(error)


@router.post("/send", response_model=ApiResponse)
def send_uart_command(request: UartSendStringRequest):
    try:
        return ok(
            "UART command sent successfully.",
            uart_service.send_uart_string(request.command),
        )
    except Exception as error:
        return error_from_exception(error)


@router.patch("", response_model=ApiResponse)
def update_uart_config(update: UartConfigUpdate):
    try:
        return ok("UART config updated successfully.", uart_service.update_uart_config(update))
    except Exception as error:
        return error_from_exception(error)


@router.put("", response_model=ApiResponse)
def replace_uart_config(config: UartConfig):
    try:
        data = uart_service.update_uart_config(UartConfigUpdate(**config.model_dump()))
        return ok("UART config replaced successfully.", data)
    except Exception as error:
        return error_from_exception(error)
