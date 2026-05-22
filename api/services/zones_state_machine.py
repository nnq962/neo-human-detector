from api.models.zones_state_machine import (
    ZonesStateMachineConfig,
    ZonesStateMachineConfigUpdate,
)
from api.services import config_store


def _model_dump(model, **kwargs) -> dict:
    return model.model_dump(**kwargs)


def _normalize_zones_state_machine_config(config: dict) -> dict:
    return ZonesStateMachineConfig(
        zone_check_mode=config.get("zone_check_mode", "center"),
        confirm_enter_time=config.get("confirm_enter_time", 5.0),
        confirm_exit_time=config.get("confirm_exit_time", 5.0),
        pending_enter_miss_grace_time=config.get("pending_enter_miss_grace_time", 1.5),
    ).model_dump()


def get_zones_state_machine_config() -> dict:
    config = config_store.get_config_data()

    return _normalize_zones_state_machine_config(config.get("zones_state_machine", {}))


def update_zones_state_machine_config(update: ZonesStateMachineConfigUpdate) -> dict:
    config = config_store.get_config_data()
    update_data = _model_dump(update, exclude_none=True, exclude_unset=True)

    if update_data:
        zones_state_machine_config = config.setdefault("zones_state_machine", {})
        zones_state_machine_config.update(update_data)
        config_store.save_config_data(config)

    return get_zones_state_machine_config()

