from fastapi import HTTPException, status

from api.models.uart import UartConfig, UartConfigUpdate
from api.services import config_store


def _model_dump(model, **kwargs) -> dict:
    return model.model_dump(**kwargs)


def _normalize_uart_config(config: dict) -> dict:
    return UartConfig(
        port=config.get("port", "/dev/ttyS4"),
        baudrate=config.get("baudrate", 115200),
    ).model_dump()


def get_uart_config() -> dict:
    config = config_store.get_config_data()

    return _normalize_uart_config(config.get("uart", {}))


def get_uart_status() -> dict:
    from uart.uart_manager import uart_manager

    return {
        **get_uart_config(),
        "runtime": uart_manager.status(),
    }


def update_uart_config(update: UartConfigUpdate) -> dict:
    update_data = _model_dump(update, exclude_none=True, exclude_unset=True)

    if update_data:
        def mutate(config: dict) -> dict:
            uart_config = config.setdefault("uart", {})
            uart_config.update(update_data)
            uart_config = _normalize_uart_config(uart_config)
            config["uart"] = uart_config
            return uart_config

        uart_config = config_store.update_config_data(mutate)

        from uart.uart_manager import uart_manager

        uart_manager.reconfigure(
            port=uart_config["port"],
            baudrate=uart_config["baudrate"],
        )
        return uart_config

    return get_uart_config()


def send_uart_string(command: str) -> dict:
    command = command.strip()
    if not command:
        raise ValueError("UART command must not be empty.")

    from uart.uart_manager import uart_manager

    sent = uart_manager.send_string(command)
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="UART is not connected or command could not be sent.",
        )

    return {
        "sent": True,
        "command": command,
    }
