"""Binary sensors for Jacuzzi ProLink."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import JacuzziConfigEntry
from .entity import JacuzziEntity
from .protocol import SpaStatus


@dataclass(frozen=True, kw_only=True)
class JacuzziBinaryDescription(BinarySensorEntityDescription):
    """Describes a binary sensor read from the status frame."""

    value_fn: Callable[[SpaStatus], bool]


BINARY_SENSORS: tuple[JacuzziBinaryDescription, ...] = (
    JacuzziBinaryDescription(
        key="filter_cycle",
        translation_key="filter_cycle",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda s: bool(s.primary_on),
    ),
    JacuzziBinaryDescription(
        key="clearray",
        translation_key="clearray",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda s: bool(s.uv_on),
    ),
    JacuzziBinaryDescription(
        key="flow",
        translation_key="flow",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: bool(s.flow_switch),
    ),
    JacuzziBinaryDescription(
        key="panel_lock",
        translation_key="panel_lock",
        device_class=BinarySensorDeviceClass.LOCK,
        # LOCK device class: on means unlocked
        value_fn=lambda s: not (s.setting_lock or s.access_lock or s.service_lock),
    ),
    JacuzziBinaryDescription(
        key="error",
        translation_key="error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda s: s.error_code != 0,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JacuzziConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        JacuzziBinarySensor(coordinator, d) for d in BINARY_SENSORS
    ]
    entities.append(JacuzziConnectivitySensor(coordinator))
    async_add_entities(entities)


class JacuzziBinarySensor(JacuzziEntity, BinarySensorEntity):
    """A flag from the status frame."""

    entity_description: JacuzziBinaryDescription

    def __init__(self, coordinator, description: JacuzziBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        status = self.coordinator.client.status
        return None if status is None else self.entity_description.value_fn(status)


class JacuzziConnectivitySensor(JacuzziEntity, BinarySensorEntity):
    """Whether the ProLink module is currently sending us data."""

    _attr_translation_key = "connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "connected")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.client.connected
