"""Lights for Jacuzzi ProLink."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import JacuzziConfigEntry
from .entity import JacuzziEntity
from .protocol import LIGHT_BRIGHTNESS_STEP, build_set_light_brightness


def to_spa_percent(ha_brightness: int) -> int:
    """Home Assistant brightness (1-255) to the nearest panel step, at least one step."""
    percent = ha_brightness * 100 / 255
    step = round(percent / LIGHT_BRIGHTNESS_STEP) * LIGHT_BRIGHTNESS_STEP
    return min(100, max(LIGHT_BRIGHTNESS_STEP, step))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JacuzziConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([JacuzziLight(entry.runtime_data)])


class JacuzziLight(JacuzziEntity, LightEntity):
    """The spa lights, dimmable in the panel's 20 % steps."""

    _attr_translation_key = "lights"
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "lights")
        self._last_percent = 100

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.client.lights is not None

    @property
    def is_on(self) -> bool | None:
        lights = self.coordinator.client.lights
        return None if lights is None else lights.on

    @property
    def brightness(self) -> int | None:
        lights = self.coordinator.client.lights
        if lights is None or not lights.on:
            return None
        if lights.brightness:
            self._last_percent = lights.brightness
        return round(lights.brightness * 255 / 100)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            percent = to_spa_percent(kwargs[ATTR_BRIGHTNESS])
        else:
            percent = self._last_percent
        await self._send(percent)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send(0)

    async def _send(self, percent: int) -> None:
        def confirmed() -> bool:
            lights = self.coordinator.client.lights
            if lights is None:
                return False
            if percent == 0:
                return not lights.on
            return lights.on and lights.brightness == percent

        await self._async_command(build_set_light_brightness(percent), confirmed)
