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


def update_uart_config(update: UartConfigUpdate) -> dict:
    config = config_store.get_config_data()
    update_data = _model_dump(update, exclude_none=True, exclude_unset=True)

    if update_data:
        uart_config = config.setdefault("uart", {})
        uart_config.update(update_data)
        config_store.save_config_data(config)

    return get_uart_config()

