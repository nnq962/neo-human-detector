from fastapi import APIRouter

from api.models.response import ApiResponse
from api.models.uart import UartConfig, UartConfigUpdate
from api.routes.responses import error_from_exception, ok
from api.services import uart as uart_service


router = APIRouter()


@router.get("", response_model=ApiResponse)
def get_uart_config():
    try:
        return ok("UART config loaded successfully.", uart_service.get_uart_config())
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
