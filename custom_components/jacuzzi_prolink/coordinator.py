"""Push coordinator: the client tells us when something changed."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import DROP_GRACE, ProLinkClient
from .const import DOMAIN

if TYPE_CHECKING:
    from . import JacuzziConfigEntry

_LOGGER = logging.getLogger(__name__)


class JacuzziCoordinator(DataUpdateCoordinator[ProLinkClient]):
    """Fans client updates out to entities. No polling."""

    config_entry: JacuzziConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: JacuzziConfigEntry, client: ProLinkClient
    ) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN)
        self.client = client
        self.data = client
        self._grace_timer: Callable[[], None] | None = None
        client.on_update = self._handle_client_update

    @callback
    def _handle_client_update(self) -> None:
        self.async_set_updated_data(self.client)
        if not self.client.connected and self._grace_timer is None:
            # Re-check availability once a short drop's grace period is over
            self._grace_timer = async_call_later(
                self.hass, DROP_GRACE + 1, self._grace_expired
            )

    @callback
    def _grace_expired(self, _now: datetime) -> None:
        self._grace_timer = None
        self.async_update_listeners()

    @callback
    def cancel_timers(self) -> None:
        if self._grace_timer is not None:
            self._grace_timer()
            self._grace_timer = None
