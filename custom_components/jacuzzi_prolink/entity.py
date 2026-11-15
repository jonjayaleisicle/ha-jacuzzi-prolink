"""Base entity for Jacuzzi ProLink."""

from __future__ import annotations

import time

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import JacuzziCoordinator
from .protocol import build_button_press

# After a simulated button press, ignore further requests for this long
# unless the spa confirms the change sooner. Presses toggle, so a second
# press before the spa reports the first would undo it.
PRESS_SETTLE_SECONDS = 5.0


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


class JacuzziToggleEntity(JacuzziEntity):
    """Something the panel turns on and off with one button that toggles."""

    _button_code: int

    def __init__(self, coordinator: JacuzziCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._settle_until = 0.0
        self._pressed_from: bool | None = None

    @property
    def _current(self) -> bool | None:
        raise NotImplementedError

    @property
    def is_on(self) -> bool | None:
        return self._current

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._pressed_from is not None and self._current != self._pressed_from:
            self._pressed_from = None  # the spa confirmed the press
            self._settle_until = 0.0
        super()._handle_coordinator_update()

    async def _async_set(self, want: bool) -> None:
        current = self._current
        if current is None or current == want:
            return
        if time.monotonic() < self._settle_until:
            return  # still waiting for the spa to report the last press
        try:
            await self.coordinator.client.send(build_button_press(self._button_code))
        except (OSError, ConnectionError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="not_connected"
            ) from err
        self._pressed_from = current
        self._settle_until = time.monotonic() + PRESS_SETTLE_SECONDS

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_set(False)
