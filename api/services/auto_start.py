from api.models.auto_start import AutoStartConfig, AutoStartConfigUpdate
from api.services import config_store


def _model_dump(model, **kwargs) -> dict:
    return model.model_dump(**kwargs)


def _normalize_auto_start_config(value) -> dict:
    return AutoStartConfig(
        auto_start=False if value is None else value,
    ).model_dump()


def get_auto_start_config() -> dict:
    config = config_store.get_config_data()

    return _normalize_auto_start_config(config.get("auto_start"))


def update_auto_start_config(update: AutoStartConfigUpdate) -> dict:
    update_data = _model_dump(update, exclude_none=True, exclude_unset=True)

    if not update_data:
        return get_auto_start_config()

    auto_start_config = _normalize_auto_start_config(update_data.get("auto_start"))

    def mutate(config: dict) -> dict:
        config["auto_start"] = auto_start_config["auto_start"]
        return auto_start_config

    return config_store.update_config_data(mutate)


def replace_auto_start_config(config: AutoStartConfig) -> dict:
    auto_start_config = _normalize_auto_start_config(config.auto_start)

    def mutate(app_config: dict) -> dict:
        app_config["auto_start"] = auto_start_config["auto_start"]
        return auto_start_config

    return config_store.update_config_data(mutate)
