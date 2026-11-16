"""Buttons for Jacuzzi ProLink."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import JacuzziConfigEntry
from .entity import JacuzziEntity
from .protocol import build_set_datetime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JacuzziConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([JacuzziSyncClockButton(entry.runtime_data)])


class JacuzziSyncClockButton(JacuzziEntity, ButtonEntity):
    """Set the spa's date and clock to Home Assistant's local time."""

    _attr_translation_key = "sync_clock"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "sync_clock")

    async def async_press(self) -> None:
        now = dt_util.now()
        frame = build_set_datetime(now.year, now.month, now.day, now.hour, now.minute)
        wanted = (now.year, now.month, now.day, now.hour * 60 + now.minute)

        def confirmed() -> bool:
            s = self.coordinator.client.status
            if s is None or (s.year, s.month, s.day) != wanted[:3]:
                return False
            # The spa's clock may tick over to the next minute before it reports
            return 0 <= s.hour * 60 + s.minute - wanted[3] <= 1

        await self._async_command(frame, confirmed)
