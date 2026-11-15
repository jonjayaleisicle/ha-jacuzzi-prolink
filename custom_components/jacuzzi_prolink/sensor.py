"""Sensors for Jacuzzi ProLink."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import JacuzziConfigEntry
from .client import ProLinkClient
from .entity import JacuzziEntity
from .protocol import TSCALE_C, SpaStatus

PUMP_STATES = ["off", "low", "high"]

# From the ProLink app (SpaWifiState), see docs in the README credits
WIFI_STATES = {
    0: "unknown",
    1: "soft_ap_unavailable",
    2: "soft_ap_available",
    3: "infrastructure",
    4: "connected_no_cloud",
    5: "connected_cloud",
    14: "linking",
    15: "not_communicating",
}


def _pump(index: int) -> Callable[[SpaStatus], str | None]:
    def value(status: SpaStatus) -> str | None:
        state = status.pump_states[index]
        return PUMP_STATES[state] if state < len(PUMP_STATES) else None

    return value


@dataclass(frozen=True, kw_only=True)
class JacuzziSensorDescription(SensorEntityDescription):
    """Describes a sensor read from the status frame."""

    value_fn: Callable[[SpaStatus], float | int | str | None]
    is_temperature: bool = False


SENSORS: tuple[JacuzziSensorDescription, ...] = (
    JacuzziSensorDescription(
        key="water_temperature",
        translation_key="water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        is_temperature=True,
        value_fn=lambda s: s.current_temp,
    ),
    JacuzziSensorDescription(
        key="target_temperature",
        translation_key="target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        is_temperature=True,
        value_fn=lambda s: s.set_temp,
    ),
    JacuzziSensorDescription(
        key="plumbing_temperature",
        translation_key="plumbing_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        is_temperature=True,
        # Decoding unconfirmed (a J-480 at 18.5 C reports 34 C here)
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.second_temp,
    ),
    JacuzziSensorDescription(
        key="circulation_pump",
        translation_key="circulation_pump",
        device_class=SensorDeviceClass.ENUM,
        options=PUMP_STATES,
        value_fn=_pump(0),
    ),
    JacuzziSensorDescription(
        key="pump_1",
        translation_key="pump_1",
        device_class=SensorDeviceClass.ENUM,
        options=PUMP_STATES,
        value_fn=_pump(1),
    ),
    JacuzziSensorDescription(
        key="pump_2",
        translation_key="pump_2",
        device_class=SensorDeviceClass.ENUM,
        options=PUMP_STATES,
        value_fn=_pump(2),
    ),
    JacuzziSensorDescription(
        key="pump_3",
        translation_key="pump_3",
        device_class=SensorDeviceClass.ENUM,
        options=PUMP_STATES,
        value_fn=_pump(3),
    ),
    JacuzziSensorDescription(
        key="error_code",
        translation_key="error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.error_code,
    ),
    JacuzziSensorDescription(
        key="heat_mode_state",
        translation_key="heat_mode_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.heat_mode_state,
    ),
    JacuzziSensorDescription(
        key="spa_state",
        translation_key="spa_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.spa_state,
    ),
    JacuzziSensorDescription(
        key="spa_clock",
        translation_key="spa_clock",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: f"{s.hour:02d}:{s.minute:02d}",
    ),
    JacuzziSensorDescription(
        key="wifi_state",
        translation_key="wifi_state",
        device_class=SensorDeviceClass.ENUM,
        options=sorted(set(WIFI_STATES.values())),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: None
        if s.wifi_state is None
        else WIFI_STATES.get(s.wifi_state, "unknown"),
    ),
    JacuzziSensorDescription(
        key="clearray_time",
        translation_key="clearray_time",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.clearray_time,
    ),
    JacuzziSensorDescription(
        key="water_time",
        translation_key="water_time",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.water_time,
    ),
    JacuzziSensorDescription(
        key="outer_filter_time",
        translation_key="outer_filter_time",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.outer_filter_time,
    ),
    JacuzziSensorDescription(
        key="inner_filter_time",
        translation_key="inner_filter_time",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.inner_filter_time,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JacuzziConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        JacuzziSensor(coordinator, description) for description in SENSORS
    ]
    entities += [
        JacuzziLightBrightnessSensor(coordinator),
        JacuzziLastUpdateSensor(coordinator),
    ]
    async_add_entities(entities)


class JacuzziSensor(JacuzziEntity, SensorEntity):
    """A value from the status frame."""

    entity_description: JacuzziSensorDescription

    def __init__(self, coordinator, description: JacuzziSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | str | None:
        status = self.coordinator.client.status
        return None if status is None else self.entity_description.value_fn(status)

    @property
    def native_unit_of_measurement(self) -> str | None:
        if not self.entity_description.is_temperature:
            return None
        status = self.coordinator.client.status
        if status is not None and status.temp_scale == TSCALE_C:
            return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT


class JacuzziLightBrightnessSensor(JacuzziEntity, SensorEntity):
    """Light brightness level from the 0x23 lights message."""

    _attr_translation_key = "light_brightness"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "light_brightness")

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.client.lights is not None

    @property
    def native_value(self) -> int | None:
        lights = self.coordinator.client.lights
        return None if lights is None else lights.brightness

    @property
    def extra_state_attributes(self) -> dict[str, int] | None:
        lights = self.coordinator.client.lights
        if lights is None:
            return None
        return {
            "mode": lights.mode,
            "red": lights.red,
            "green": lights.green,
            "blue": lights.blue,
        }


class JacuzziLastUpdateSensor(JacuzziEntity, SensorEntity):
    """When the last status frame arrived."""

    _attr_translation_key = "last_update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "last_update")

    @property
    def available(self) -> bool:
        return self.coordinator.client.last_status_at is not None

    @property
    def native_value(self) -> datetime | None:
        client: ProLinkClient = self.coordinator.client
        return client.last_status_at
