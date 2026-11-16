"""Config flow and entity setup."""

from unittest.mock import patch

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

from .frames import J480_STATUS, J480_STATUS_JETS_OFF as J480_STATUS_JETS_OFF_FOR_LIGHTS, STATUS

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


async def _setup(hass: HomeAssistant) -> tuple[MockConfigEntry, list]:
    """Set up the integration with a fake client that records commands.

    Each recorded command is (frame, confirmed): the bytes the entity sent and
    the check it would use to recognise the spa's response.
    """
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
    sent: list = []

    async def record(frame, confirmed, **kwargs):
        sent.append((frame, confirmed))

    entry.runtime_data.client.send_and_confirm = record
    return entry, sent


async def _feed(hass: HomeAssistant, entry, *frames: bytes) -> None:
    for raw in frames:
        entry.runtime_data.client.handle_frame(parse_frame(raw))
    await hass.async_block_till_done()


async def _call(hass: HomeAssistant, domain: str, service: str, entity_id: str, **data):
    await hass.services.async_call(
        domain, service, {"entity_id": entity_id, **data}, blocking=True
    )


async def test_sync_clock_button(hass: HomeAssistant, freezer) -> None:
    from .frames import J480_STATUS_AFTER_CLOCK_SYNC

    await hass.config.async_set_time_zone("Europe/London")
    freezer.move_to("2026-11-15 21:52:10+00:00")
    entry, sent = await _setup(hass)
    assert hass.states.get("button.spa_sync_spa_clock").state == STATE_UNAVAILABLE

    await _feed(hass, entry, J480_STATUS)  # clock unset: 2 Jan 2014
    await _call(hass, "button", "press", "button.spa_sync_spa_clock")
    frame, confirmed = sent[-1]
    assert frame == build_set_datetime(2026, 11, 15, 21, 52)
    assert not confirmed()
    await _feed(hass, entry, J480_STATUS_AFTER_CLOCK_SYNC)  # real response
    assert confirmed()

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_climate_sets_temperature(hass: HomeAssistant) -> None:
    from .frames import J480_STATUS_SET_20_5

    entry, sent = await _setup(hass)
    await _feed(hass, entry, J480_STATUS)

    state = hass.states.get("climate.spa")
    assert state.state == "heat"
    assert state.attributes["current_temperature"] == 18.5
    assert state.attributes["temperature"] == 18.5
    assert state.attributes["min_temp"] == 18.5
    assert state.attributes["max_temp"] == 40.0

    await _call(hass, "climate", "set_temperature", "climate.spa", temperature=20.5)
    frame, confirmed = sent[-1]
    assert frame == build_set_temperature(20.5, TSCALE_C)
    assert not confirmed()
    await _feed(hass, entry, J480_STATUS_SET_20_5)  # real response
    assert confirmed()

    with pytest.raises(ServiceValidationError):
        await _call(hass, "climate", "set_temperature", "climate.spa", temperature=18.0)
    assert len(sent) == 1

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_jets_toggle(hass: HomeAssistant) -> None:
    from custom_components.jacuzzi_prolink.protocol import (
        BUTTON_JETS_1,
        build_button_press,
    )

    from .frames import J480_STATUS_JETS_1_ON, J480_STATUS_JETS_OFF

    entry, sent = await _setup(hass)
    await _feed(hass, entry, J480_STATUS_JETS_OFF)
    assert hass.states.get("switch.spa_jets_1").state == "off"
    assert hass.states.get("switch.spa_jets_2").state == "off"

    # Turning off something already off sends nothing
    await _call(hass, "switch", "turn_off", "switch.spa_jets_1")
    assert sent == []

    await _call(hass, "switch", "turn_on", "switch.spa_jets_1")
    frame, confirmed = sent[-1]
    assert frame == build_button_press(BUTTON_JETS_1)
    assert not confirmed()
    await _feed(hass, entry, J480_STATUS_JETS_1_ON)
    assert confirmed()
    assert hass.states.get("switch.spa_jets_1").state == "on"

    # Already on: a repeat request must not press again (that would turn it off)
    await _call(hass, "switch", "turn_on", "switch.spa_jets_1")
    assert len(sent) == 1

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_lights_brightness(hass: HomeAssistant) -> None:
    from custom_components.jacuzzi_prolink.protocol import build_set_light_brightness

    from .frames import J480_LIGHTS_FROM_HA_20, J480_LIGHTS_OFF, J480_LIGHTS_ON

    entry, sent = await _setup(hass)
    await _feed(hass, entry, J480_STATUS_JETS_OFF_FOR_LIGHTS, J480_LIGHTS_OFF)
    assert hass.states.get("light.spa_lights").state == "off"

    await _call(hass, "light", "turn_on", "light.spa_lights")
    frame, confirmed = sent[-1]
    assert frame == build_set_light_brightness(100)
    await _feed(hass, entry, J480_LIGHTS_ON)  # 100 % from the panel capture
    assert confirmed()
    state = hass.states.get("light.spa_lights")
    assert state.state == "on"
    assert state.attributes["brightness"] == 255

    # Brightness snaps to the panel's 20 % steps
    await _call(hass, "light", "turn_on", "light.spa_lights", brightness_pct=23)
    frame, confirmed = sent[-1]
    assert frame == build_set_light_brightness(20)
    assert not confirmed()
    await _feed(hass, entry, J480_LIGHTS_FROM_HA_20)
    assert confirmed()

    await _call(hass, "light", "turn_off", "light.spa_lights")
    frame, confirmed = sent[-1]
    assert frame == build_set_light_brightness(0)
    assert not confirmed()
    await _feed(hass, entry, J480_LIGHTS_OFF)
    assert confirmed()

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_command_errors_are_reported(hass: HomeAssistant) -> None:
    from custom_components.jacuzzi_prolink.client import CommandNotConfirmed

    entry, sent = await _setup(hass)
    await _feed(hass, entry, J480_STATUS)
    client = entry.runtime_data.client

    async def ignored(frame, confirmed, **kwargs):
        raise CommandNotConfirmed(frame.hex())

    client.send_and_confirm = ignored
    with pytest.raises(HomeAssistantError, match="did not respond"):
        await _call(hass, "climate", "set_temperature", "climate.spa", temperature=20)

    async def unreachable(frame, confirmed, **kwargs):
        raise ConnectionError

    client.send_and_confirm = unreachable
    with pytest.raises(HomeAssistantError, match="not connected"):
        await _call(hass, "button", "press", "button.spa_sync_spa_clock")

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_heat_mode_select_and_heating(hass: HomeAssistant) -> None:
    from custom_components.jacuzzi_prolink.protocol import (
        HEAT_MODE_AUTO,
        build_set_heat_mode,
    )

    from .frames import J480_STATUS_AUTO_HEATING, J480_STATUS_ECO_IDLE

    entry, sent = await _setup(hass)
    await _feed(hass, entry, J480_STATUS_ECO_IDLE)
    assert hass.states.get("select.spa_heat_mode").state == "eco"
    assert hass.states.get("binary_sensor.spa_heating").state == "off"
    assert hass.states.get("climate.spa").attributes["hvac_action"] == "idle"

    # Choosing the current mode sends nothing
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.spa_heat_mode", "option": "eco"}, blocking=True,
    )
    assert sent == []

    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.spa_heat_mode", "option": "auto"}, blocking=True,
    )
    frame, confirmed = sent[-1]
    assert frame == build_set_heat_mode(HEAT_MODE_AUTO)
    assert not confirmed()
    await _feed(hass, entry, J480_STATUS_AUTO_HEATING)  # real panel capture
    assert confirmed()
    assert hass.states.get("select.spa_heat_mode").state == "auto"
    assert hass.states.get("binary_sensor.spa_heating").state == "on"
    assert hass.states.get("climate.spa").attributes["hvac_action"] == "heating"

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_secondary_filter_select(hass: HomeAssistant) -> None:
    from custom_components.jacuzzi_prolink.protocol import (
        FILTER2_INFREQUENT,
        build_set_filter2_mode,
    )

    from .frames import J480_STATUS_FILTER_AWAY, J480_STATUS_FILTER_INFREQUENT

    entry, sent = await _setup(hass)
    await _feed(hass, entry, J480_STATUS_FILTER_AWAY)
    assert hass.states.get("select.spa_secondary_filter").state == "away"

    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.spa_secondary_filter", "option": "infrequent"},
        blocking=True,
    )
    frame, confirmed = sent[-1]
    assert frame == build_set_filter2_mode(FILTER2_INFREQUENT)
    assert not confirmed()
    await _feed(hass, entry, J480_STATUS_FILTER_INFREQUENT)
    assert confirmed()
    assert hass.states.get("select.spa_secondary_filter").state == "infrequent"

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_connection_drops_sensor_survives_restart(hass: HomeAssistant) -> None:
    from homeassistant.core import State
    from pytest_homeassistant_custom_component.common import (
        mock_restore_cache_with_extra_data,
    )

    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("sensor.spa_connection_drops", "7"),
                {"native_value": 7, "native_unit_of_measurement": None},
            )
        ],
    )
    entry, _ = await _setup(hass)
    client = entry.runtime_data.client

    # Shown even before the spa has connected
    assert hass.states.get("sensor.spa_connection_drops").state == "7"

    await _feed(hass, entry, J480_STATUS)
    client._set_connected(False)  # the module drops the connection
    await hass.async_block_till_done()
    state = hass.states.get("sensor.spa_connection_drops")
    assert state.state == "8"
    assert state.attributes["last_drop"] is not None

    await _feed(hass, entry, J480_STATUS)  # back again
    assert hass.states.get("sensor.spa_connection_drops").attributes["last_reconnect"]

    assert await hass.config_entries.async_unload(entry.entry_id)
