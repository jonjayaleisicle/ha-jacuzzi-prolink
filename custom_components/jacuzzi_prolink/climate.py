"""Thermostat for Jacuzzi ProLink."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import PRECISION_HALVES, PRECISION_WHOLE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import JacuzziConfigEntry
from .const import DOMAIN
from .entity import JacuzziEntity
from .protocol import (
    MAX_TEMP_C,
    MAX_TEMP_F,
    MIN_TEMP_C,
    MIN_TEMP_F,
    TSCALE_C,
    build_set_temperature,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JacuzziConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([JacuzziClimate(entry.runtime_data)])


class JacuzziClimate(JacuzziEntity, ClimateEntity):
    """Water temperature and set point. The spa always heats to the set point."""

    _attr_name = None  # the device's own name, e.g. "Spa"
    _attr_hvac_modes = [HVACMode.HEAT]
    _attr_hvac_mode = HVACMode.HEAT
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "climate")

    @property
    def _celsius(self) -> bool:
        status = self.coordinator.client.status
        return status is None or status.temp_scale == TSCALE_C

    @property
    def temperature_unit(self) -> str:
        return UnitOfTemperature.CELSIUS if self._celsius else UnitOfTemperature.FAHRENHEIT

    @property
    def precision(self) -> float:
        return PRECISION_HALVES if self._celsius else PRECISION_WHOLE

    @property
    def target_temperature_step(self) -> float:
        return 0.5 if self._celsius else 1.0

    @property
    def min_temp(self) -> float:
        return MIN_TEMP_C if self._celsius else MIN_TEMP_F

    @property
    def max_temp(self) -> float:
        return MAX_TEMP_C if self._celsius else MAX_TEMP_F

    @property
    def current_temperature(self) -> float | None:
        status = self.coordinator.client.status
        return None if status is None else status.current_temp

    @property
    def hvac_action(self) -> HVACAction | None:
        status = self.coordinator.client.status
        if status is None:
            return None
        return HVACAction.HEATING if status.heating else HVACAction.IDLE

    @property
    def target_temperature(self) -> float | None:
        status = self.coordinator.client.status
        return None if status is None else status.set_temp

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Heat is the only mode; nothing to change."""

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        status = self.coordinator.client.status
        if temp is None or status is None:
            return
        try:
            frame = build_set_temperature(temp, status.temp_scale)
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="temperature_out_of_range",
                translation_placeholders={
                    "min": str(self.min_temp),
                    "max": str(self.max_temp),
                    "unit": self.temperature_unit,
                },
            ) from err
        wanted = round(temp * 2) / 2 if self._celsius else round(temp)

        def confirmed() -> bool:
            current = self.coordinator.client.status
            return current is not None and current.set_temp == wanted

        await self._async_command(frame, confirmed)
