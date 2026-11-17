"""The Jacuzzi ProLink integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .client import ProLinkClient, async_probe
from .coordinator import JacuzziCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.LIGHT,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

type JacuzziConfigEntry = ConfigEntry[JacuzziCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: JacuzziConfigEntry) -> bool:
    """Set up a spa from a config entry."""
    host: str = entry.data[CONF_HOST]
    port: int = entry.data[CONF_PORT]

    try:
        await async_probe(host, port)
    except (OSError, TimeoutError) as err:
        raise ConfigEntryNotReady(
            f"Cannot reach the ProLink module at {host}:{port}: {err}"
        ) from err

    client = ProLinkClient(host, port)
    coordinator = JacuzziCoordinator(hass, entry, client)
    entry.runtime_data = coordinator

    # Cancelled automatically when the entry unloads or Home Assistant stops
    entry.async_create_background_task(
        hass, client.run(), f"jacuzzi_prolink {host}:{port}"
    )
    async def _close() -> None:
        coordinator.cancel_timers()
        await client.close()

    entry.async_on_unload(_close)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: JacuzziConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
