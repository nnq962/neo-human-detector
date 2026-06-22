from api.models.zone_state_machine import (
    ZoneStateMachineConfig,
    ZoneStateMachineConfigUpdate,
)
from api.services import config_store


def _model_dump(model, **kwargs) -> dict:
    return model.model_dump(**kwargs)


def _normalize_zone_state_machine_config(config: dict) -> dict:
    return ZoneStateMachineConfig(
        confirm_enter_time=config.get("confirm_enter_time", 5.0),
        confirm_exit_time=config.get("confirm_exit_time", 5.0),
        pending_enter_miss_grace_time=config.get("pending_enter_miss_grace_time", 1.5),
    ).model_dump()


def get_zone_state_machine_config() -> dict:
    config = config_store.get_config_data()

    return _normalize_zone_state_machine_config(config.get("zone_state_machine", {}))


def update_zone_state_machine_config(update: ZoneStateMachineConfigUpdate) -> dict:
    update_data = _model_dump(update, exclude_none=True, exclude_unset=True)

    if update_data:
        def mutate(config: dict) -> None:
            zone_state_machine_config = config.setdefault("zone_state_machine", {})
            zone_state_machine_config.update(update_data)

        config_store.update_config_data(mutate)

    return get_zone_state_machine_config()
