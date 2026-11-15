"""Lights for Jacuzzi ProLink."""

from __future__ import annotations

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import JacuzziConfigEntry
from .entity import JacuzziToggleEntity
from .protocol import BUTTON_LIGHTS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JacuzziConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([JacuzziLight(entry.runtime_data)])


class JacuzziLight(JacuzziToggleEntity, LightEntity):
    """The spa lights, toggled like the panel's lights button."""

    _attr_translation_key = "lights"
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _button_code = BUTTON_LIGHTS

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "lights")

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.client.lights is not None

    @property
    def _current(self) -> bool | None:
        lights = self.coordinator.client.lights
        return None if lights is None else lights.on
