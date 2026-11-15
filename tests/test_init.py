"""Config flow and entity setup."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jacuzzi_prolink.const import DOMAIN
from custom_components.jacuzzi_prolink.protocol import parse_frame

from .frames import STATUS

PROBE = "custom_components.jacuzzi_prolink.{}.async_probe"


async def _never_ending(self):
    """Stand-in for ProLinkClient.run: the test feeds frames directly."""


async def test_config_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    with patch(PROBE.format("config_flow"), side_effect=OSError):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.0.2.10", CONF_PORT: 4257}
        )
    assert result["errors"] == {"base": "cannot_connect"}

    with (
        patch(PROBE.format("config_flow")),
        patch("custom_components.jacuzzi_prolink.async_probe"),
        patch(
            "custom_components.jacuzzi_prolink.client.ProLinkClient.run", _never_ending
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.0.2.10", CONF_PORT: 4257}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "192.0.2.10", CONF_PORT: 4257}
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is config_entries.ConfigEntryState.LOADED


async def test_entities_follow_status(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: "192.0.2.10", CONF_PORT: 4257}, title="Spa"
    )
    entry.add_to_hass(hass)
    with (
        patch("custom_components.jacuzzi_prolink.async_probe"),
        patch(
            "custom_components.jacuzzi_prolink.client.ProLinkClient.run", _never_ending
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get("sensor.spa_water_temperature").state == STATE_UNAVAILABLE
    assert hass.states.get("binary_sensor.spa_connected").state == "off"

    entry.runtime_data.client.handle_frame(parse_frame(STATUS))
    await hass.async_block_till_done()

    water = hass.states.get("sensor.spa_water_temperature")
    assert float(water.state) == 38.0
    assert water.attributes["unit_of_measurement"] == "°C"
    assert hass.states.get("sensor.spa_pump_1").state == "high"
    assert hass.states.get("sensor.spa_pump_2").state == "off"
    assert hass.states.get("binary_sensor.spa_error").state == "off"
    assert hass.states.get("binary_sensor.spa_connected").state == "on"
    assert hass.states.get("sensor.spa_spa_clock").state == "16:18"

    assert await hass.config_entries.async_unload(entry.entry_id)
