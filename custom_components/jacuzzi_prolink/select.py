"""Selects for Jacuzzi ProLink."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import JacuzziConfigEntry
from .entity import JacuzziEntity
from .protocol import (
    FILTER2_AWAY,
    FILTER2_FREQUENT,
    FILTER2_INFREQUENT,
    HEAT_MODE_AUTO,
    HEAT_MODE_DAY,
    HEAT_MODE_ECO,
    SpaStatus,
    build_set_filter2_mode,
    build_set_heat_mode,
)

HEAT_MODES = {"auto": HEAT_MODE_AUTO, "eco": HEAT_MODE_ECO, "day": HEAT_MODE_DAY}
FILTER2_MODES = {
    "frequent": FILTER2_FREQUENT,
    "infrequent": FILTER2_INFREQUENT,
    "away": FILTER2_AWAY,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JacuzziConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [JacuzziHeatModeSelect(coordinator), JacuzziFilter2Select(coordinator)]
    )


class JacuzziModeSelect(JacuzziEntity, SelectEntity):
    """A setting the spa reports in its status and sets with one command."""

    _modes: dict[str, int]

    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._attr_options = list(self._modes)

    def _read(self, status: SpaStatus) -> int:
        raise NotImplementedError

    def _build(self, mode: int) -> bytes:
        raise NotImplementedError

    @property
    def current_option(self) -> str | None:
        status = self.coordinator.client.status
        if status is None:
            return None
        value = self._read(status)
        return next((name for name, v in self._modes.items() if v == value), None)

    async def async_select_option(self, option: str) -> None:
        mode = self._modes[option]

        def confirmed() -> bool:
            status = self.coordinator.client.status
            return status is not None and self._read(status) == mode

        if confirmed():
            return
        await self._async_command(self._build(mode), confirmed)


class JacuzziHeatModeSelect(JacuzziModeSelect):
    """Auto heats at all times, Eco only 5pm-7am, Day only 7am-5pm."""

    _modes = HEAT_MODES
    _attr_icon = "mdi:radiator"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "heat_mode")

    def _read(self, status: SpaStatus) -> int:
        return status.heat_mode

    def _build(self, mode: int) -> bytes:
        return build_set_heat_mode(mode)


class JacuzziFilter2Select(JacuzziModeSelect):
    """How often the secondary filtration cycles run."""

    _modes = FILTER2_MODES
    _attr_icon = "mdi:air-filter"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "secondary_filter")

    def _read(self, status: SpaStatus) -> int:
        return status.filter2_mode

    def _build(self, mode: int) -> bytes:
        return build_set_filter2_mode(mode)
