from api.models.reid import ReIdConfig, ReIdConfigUpdate
from api.services import config_store


NESTED_SECTIONS = {"embedding", "track", "quality", "gallery"}


def _model_dump(model, **kwargs) -> dict:
    return model.model_dump(**kwargs)


def _normalize_reid_config(config: dict) -> dict:
    return ReIdConfig(**(config or {})).model_dump()


def get_reid_config() -> dict:
    config = config_store.get_config_data()

    return _normalize_reid_config(config.get("reid", {}))


def update_reid_config(update: ReIdConfigUpdate) -> dict:
    update_data = _model_dump(update, exclude_none=True, exclude_unset=True)

    if update_data:
        def mutate(config: dict) -> dict:
            reid_config = config.setdefault("reid", {})

            for key, value in update_data.items():
                if key in NESTED_SECTIONS:
                    reid_config.setdefault(key, {}).update(value)
                else:
                    reid_config[key] = value

            reid_config = _normalize_reid_config(reid_config)
            config["reid"] = reid_config
            return reid_config

        return config_store.update_config_data(mutate)

    return get_reid_config()


def replace_reid_config(config: ReIdConfig) -> dict:
    reid_config = _normalize_reid_config(_model_dump(config))

    def mutate(app_config: dict) -> dict:
        app_config["reid"] = reid_config
        return reid_config

    return config_store.update_config_data(mutate)


def delete_reid_config() -> None:
    def mutate(app_config: dict) -> None:
        app_config.pop("reid", None)

    config_store.update_config_data(mutate)
