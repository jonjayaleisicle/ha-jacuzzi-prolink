"""Selects for Jacuzzi ProLink."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import JacuzziConfigEntry
from .entity import JacuzziEntity
from .protocol import HEAT_MODE_AUTO, HEAT_MODE_DAY, HEAT_MODE_ECO, build_set_heat_mode

HEAT_MODES = {"auto": HEAT_MODE_AUTO, "eco": HEAT_MODE_ECO, "day": HEAT_MODE_DAY}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JacuzziConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([JacuzziHeatModeSelect(entry.runtime_data)])


class JacuzziHeatModeSelect(JacuzziEntity, SelectEntity):
    """Auto heats at all times, Eco only 5pm-7am, Day only 7am-5pm."""

    _attr_translation_key = "heat_mode"
    _attr_options = list(HEAT_MODES)
    _attr_icon = "mdi:radiator"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "heat_mode")

    @property
    def current_option(self) -> str | None:
        status = self.coordinator.client.status
        if status is None:
            return None
        for name, value in HEAT_MODES.items():
            if value == status.heat_mode:
                return name
        return None

    async def async_select_option(self, option: str) -> None:
        mode = HEAT_MODES[option]

        def confirmed() -> bool:
            status = self.coordinator.client.status
            return status is not None and status.heat_mode == mode

        if confirmed():
            return
        await self._async_command(build_set_heat_mode(mode), confirmed)
