"""Base entity for Jacuzzi ProLink."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import JacuzziCoordinator


class JacuzziEntity(CoordinatorEntity[JacuzziCoordinator]):
    """An entity backed by the spa's status broadcasts."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: JacuzziCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title or DEFAULT_NAME,
            manufacturer="Jacuzzi",
            model="ProLink spa",
        )

    @property
    def available(self) -> bool:
        client = self.coordinator.client
        return client.connected and client.status is not None
