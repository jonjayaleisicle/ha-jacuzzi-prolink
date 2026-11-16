"""Config flow and entity setup."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jacuzzi_prolink.const import DOMAIN
from custom_components.jacuzzi_prolink.protocol import (
    TSCALE_C,
    build_set_datetime,
    build_set_temperature,
    parse_frame,
)

from .frames import J480_STATUS, STATUS

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
    assert float(water.state) == 19.0
    assert water.attributes["unit_of_measurement"] == "°C"
    assert hass.states.get("sensor.spa_pump_1").state == "high"
    assert hass.states.get("sensor.spa_pump_2").state == "off"
    assert hass.states.get("binary_sensor.spa_error").state == "off"
    assert hass.states.get("binary_sensor.spa_connected").state == "on"
    assert hass.states.get("sensor.spa_spa_clock").state == "16:18"

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_sync_clock_button(hass: HomeAssistant, freezer) -> None:
    await hass.config.async_set_time_zone("Europe/London")
    freezer.move_to("2026-11-15 21:42:30+00:00")
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

    client = entry.runtime_data.client
    assert hass.states.get("button.spa_sync_spa_clock").state == STATE_UNAVAILABLE

    writer = MagicMock()
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    client._writer = writer
    client.handle_frame(parse_frame(STATUS))
    await hass.async_block_till_done()

    await hass.services.async_call(
        "button", "press", {"entity_id": "button.spa_sync_spa_clock"}, blocking=True
    )
    writer.write.assert_called_once_with(build_set_datetime(2026, 11, 15, 21, 42))

    # Lost connection: the press fails with a clear error instead of hanging
    client._writer = None
    with pytest.raises(HomeAssistantError):
        await client_press(hass)

    assert await hass.config_entries.async_unload(entry.entry_id)


async def client_press(hass: HomeAssistant) -> None:
    entity = hass.data["entity_components"]["button"].get_entity(
        "button.spa_sync_spa_clock"
    )
    await entity.async_press()


async def test_climate_sets_temperature(hass: HomeAssistant) -> None:
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

    client = entry.runtime_data.client
    writer = MagicMock()
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    client._writer = writer
    client.handle_frame(parse_frame(J480_STATUS))
    await hass.async_block_till_done()

    state = hass.states.get("climate.spa")
    assert state.state == "heat"
    assert state.attributes["current_temperature"] == 18.5
    assert state.attributes["temperature"] == 18.5
    assert state.attributes["min_temp"] == 18.5
    assert state.attributes["max_temp"] == 40.0

    await hass.services.async_call(
        "climate", "set_temperature",
        {"entity_id": "climate.spa", "temperature": 37.5}, blocking=True,
    )
    writer.write.assert_called_once_with(build_set_temperature(37.5, TSCALE_C))

    writer.write.reset_mock()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "climate", "set_temperature",
            {"entity_id": "climate.spa", "temperature": 18.0}, blocking=True,
        )
    writer.write.assert_not_called()

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_jets_and_lights_toggle(hass: HomeAssistant, freezer) -> None:
    from custom_components.jacuzzi_prolink.protocol import (
        BUTTON_JETS_1,
        build_button_press,
        build_set_light_brightness,
    )

    from .frames import J480_LIGHTS_OFF, J480_LIGHTS_ON, J480_STATUS_JETS_1_ON, J480_STATUS_JETS_OFF

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

    client = entry.runtime_data.client
    writer = MagicMock()
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    client._writer = writer
    client.handle_frame(parse_frame(J480_STATUS_JETS_OFF))
    client.handle_frame(parse_frame(J480_LIGHTS_OFF))
    await hass.async_block_till_done()

    assert hass.states.get("switch.spa_jets_1").state == "off"
    assert hass.states.get("switch.spa_jets_2").state == "off"
    assert hass.states.get("light.spa_lights").state == "off"

    async def call(domain, service, entity_id):
        await hass.services.async_call(
            domain, service, {"entity_id": entity_id}, blocking=True
        )

    # Turning off something already off sends nothing
    await call("switch", "turn_off", "switch.spa_jets_1")
    writer.write.assert_not_called()

    # Turning on presses the jets 1 button once
    await call("switch", "turn_on", "switch.spa_jets_1")
    writer.write.assert_called_once_with(build_button_press(BUTTON_JETS_1))

    # A second request before the spa reports back must not press again
    await call("switch", "turn_on", "switch.spa_jets_1")
    await call("switch", "turn_off", "switch.spa_jets_1")
    assert writer.write.call_count == 1

    # The spa confirms; now turning off presses again
    client.handle_frame(parse_frame(J480_STATUS_JETS_1_ON))
    await hass.async_block_till_done()
    assert hass.states.get("switch.spa_jets_1").state == "on"
    await call("switch", "turn_off", "switch.spa_jets_1")
    assert writer.write.call_count == 2

    # If the spa never confirms, presses are allowed again after the settle time
    freezer.tick(6)
    await call("switch", "turn_off", "switch.spa_jets_1")
    assert writer.write.call_count == 3

    # Every command sent is kept, timestamped, for the diagnostics download
    assert client.sent_frames[-1].endswith(build_button_press(BUTTON_JETS_1).hex())
    assert len(client.sent_frames) == 3

    writer.write.reset_mock()
    await call("light", "turn_on", "light.spa_lights")
    writer.write.assert_called_once_with(build_set_light_brightness(100))
    client.handle_frame(parse_frame(J480_LIGHTS_ON))
    await hass.async_block_till_done()
    state = hass.states.get("light.spa_lights")
    assert state.state == "on"
    assert state.attributes["brightness"] == 255

    # Brightness snaps to the panel's 20 % steps
    writer.write.reset_mock()
    await hass.services.async_call(
        "light", "turn_on",
        {"entity_id": "light.spa_lights", "brightness_pct": 47}, blocking=True,
    )
    writer.write.assert_called_once_with(build_set_light_brightness(40))

    writer.write.reset_mock()
    await call("light", "turn_off", "light.spa_lights")
    writer.write.assert_called_once_with(build_set_light_brightness(0))

    assert await hass.config_entries.async_unload(entry.entry_id)
