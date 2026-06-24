from api.models.detection import DetectionConfig, DetectionConfigUpdate
from api.services import config_store
from src.detection.model_registry import validate_model_config


def _model_dump(model, **kwargs) -> dict:
    return model.model_dump(**kwargs)


def normalize_detection_config(config: dict) -> dict:
    return DetectionConfig(**(config or {})).model_dump()


def validate_detection_config(config: dict) -> None:
    validate_model_config(
        model_size=config.get("model_size", "medium"),
        task=config.get("task", "pose"),
        batch_size=int(config.get("batch_size", 1)),
    )


def get_detection_config() -> dict:
    config = config_store.get_config_data()

    return normalize_detection_config(config.get("detection", {}))


def update_detection_config(update: DetectionConfigUpdate) -> dict:
    update_data = _model_dump(update, exclude_none=True, exclude_unset=True)

    if update_data:
        def mutate(config: dict) -> dict:
            detection_config = config.setdefault("detection", {})
            detection_config.update(update_data)
            detection_config = normalize_detection_config(detection_config)
            validate_detection_config(detection_config)
            config["detection"] = detection_config
            return detection_config

        return config_store.update_config_data(mutate)

    return get_detection_config()


def replace_detection_config(config: DetectionConfig) -> dict:
    detection_config = normalize_detection_config(_model_dump(config))
    validate_detection_config(detection_config)

    def mutate(app_config: dict) -> dict:
        app_config["detection"] = detection_config
        return detection_config

    return config_store.update_config_data(mutate)


def delete_detection_config() -> dict:
    detection_config = normalize_detection_config({})

    def mutate(app_config: dict) -> dict:
        app_config["detection"] = detection_config
        return detection_config

    return config_store.update_config_data(mutate)
