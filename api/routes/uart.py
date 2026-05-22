from fastapi import APIRouter, HTTPException

from api.models.uart import UartConfig, UartConfigUpdate
from api.services import uart as uart_service


router = APIRouter()


@router.get("", response_model=UartConfig)
def get_uart_config():
    try:
        return uart_service.get_uart_config()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("", response_model=UartConfig)
def update_uart_config(update: UartConfigUpdate):
    try:
        return uart_service.update_uart_config(update)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("", response_model=UartConfig)
def replace_uart_config(config: UartConfig):
    try:
        return uart_service.update_uart_config(UartConfigUpdate(**config.model_dump()))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

