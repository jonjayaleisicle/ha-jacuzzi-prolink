"""Diagnostics: raw frames help decode models that differ from the notes."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import JacuzziConfigEntry

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: JacuzziConfigEntry
) -> dict[str, Any]:
    client = entry.runtime_data.client
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "client": client.diagnostics(),
        "status": asdict(client.status) if client.status else None,
        "lights": asdict(client.lights) if client.lights else None,
        "filter_cycle": asdict(client.filter_cycle) if client.filter_cycle else None,
    }
