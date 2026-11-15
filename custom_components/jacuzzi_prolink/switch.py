"""Jets switches for Jacuzzi ProLink."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import JacuzziConfigEntry
from .entity import JacuzziToggleEntity
from .protocol import BUTTON_JETS_1, BUTTON_JETS_2

JETS = ((1, BUTTON_JETS_1), (2, BUTTON_JETS_2))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JacuzziConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        JacuzziJetsSwitch(entry.runtime_data, pump, code) for pump, code in JETS
    )


class JacuzziJetsSwitch(JacuzziToggleEntity, SwitchEntity):
    """A jet pump, toggled like the panel's jets button."""

    _attr_icon = "mdi:hydro-power"

    def __init__(self, coordinator, pump: int, code: int) -> None:
        super().__init__(coordinator, f"jets_{pump}")
        self._pump = pump
        self._button_code = code
        self._attr_translation_key = f"jets_{pump}"

    @property
    def _current(self) -> bool | None:
        status = self.coordinator.client.status
        return None if status is None else status.pump_states[self._pump] != 0
