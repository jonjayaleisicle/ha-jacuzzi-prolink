"""Push coordinator: the client tells us when something changed."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import ProLinkClient
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
        client.on_update = self._handle_client_update

    @callback
    def _handle_client_update(self) -> None:
        self.async_set_updated_data(self.client)
