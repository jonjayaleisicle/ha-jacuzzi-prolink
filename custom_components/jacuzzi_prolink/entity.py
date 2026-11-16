"""Base entity for Jacuzzi ProLink."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import JacuzziCoordinator
from .client import CommandNotConfirmed
from .protocol import build_button_press


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

    async def _async_command(self, frame: bytes, confirmed: Callable[[], bool]) -> None:
        """Send a command, retrying once, and fail loudly if the spa ignores it."""
        try:
            await self.coordinator.client.send_and_confirm(frame, confirmed)
        except CommandNotConfirmed as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="not_confirmed"
            ) from err
        except (OSError, ConnectionError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="not_connected"
            ) from err


class JacuzziToggleEntity(JacuzziEntity):
    """Something the panel turns on and off with one button that toggles."""

    _button_code: int

    def __init__(self, coordinator: JacuzziCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._lock = asyncio.Lock()

    @property
    def _current(self) -> bool | None:
        raise NotImplementedError

    @property
    def is_on(self) -> bool | None:
        return self._current

    async def _async_set(self, want: bool) -> None:
        # Requests queue up; each one re-reads the state after the previous
        # finished, so a double click cannot press twice and undo itself.
        async with self._lock:
            before = self._current
            if before is None or before == want:
                return
            await self._async_command(
                build_button_press(self._button_code),
                lambda: self._current is not None and self._current != before,
            )

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_set(False)
