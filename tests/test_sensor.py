"""Tests for the sensor platform (plan AD-15, AC-13)."""

from __future__ import annotations

from typing import Any

from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.bscpylgtv.sensor import POWER_STATE_OPTIONS

from .conftest import get_entity

# Re-use the long-lived setup fixture.
from .conftest import integration as _integration  # noqa: F401

SENSORS = {
    "current_app": "sensor.lg_webos_tv_oled55c2_current_app",
    "volume": "sensor.lg_webos_tv_oled55c2_volume",
    "power_state": "sensor.lg_webos_tv_oled55c2_power_state",
    "current_channel": "sensor.lg_webos_tv_oled55c2_current_channel",
}


def _entity(hass: HomeAssistant, key: str) -> Any:
    return get_entity(hass, "sensor", SENSORS[key])


async def _refresh(integration: Any) -> None:
    integration.tv.push_update()
    await integration.coordinator.hass.async_block_till_done()
    await integration.coordinator.hass.async_block_till_done()


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------


async def test_sensor_registry_shape(integration: Any) -> None:
    """Four sensors; only current_channel is DIAGNOSTIC; all enabled."""
    hass = integration.coordinator.hass
    uid = integration.entry.unique_id
    registry = er.async_get(hass)
    sensors = {
        entry.unique_id.removeprefix(f"{uid}_"): entry
        for entry in registry.entities.values()
        if entry.domain == "sensor"
        and entry.unique_id
        and entry.unique_id.startswith(uid)
    }
    assert set(sensors) == set(SENSORS)
    for key, reg in sensors.items():
        expected = EntityCategory.DIAGNOSTIC if key == "current_channel" else None
        assert reg.entity_category is expected, key
        assert reg.disabled_by is None, key


# ---------------------------------------------------------------------------
# current_app
# ---------------------------------------------------------------------------


async def test_current_app_resolves_title_via_apps_dict(integration: Any) -> None:
    hass = integration.coordinator.hass
    assert hass.states.get(SENSORS["current_app"]).state == "YouTube"


async def test_current_app_falls_back_to_raw_id(integration: Any) -> None:
    """An app missing from the apps dict shows the raw app id."""
    hass = integration.coordinator.hass
    integration.tv.current_appId = "com.webos.app.unknown"
    await _refresh(integration)
    assert hass.states.get(SENSORS["current_app"]).state == "com.webos.app.unknown"


async def test_current_app_none_renders_unknown(integration: Any) -> None:
    hass = integration.coordinator.hass
    integration.tv.current_appId = None
    await _refresh(integration)
    assert hass.states.get(SENSORS["current_app"]).state == "unknown"


# ---------------------------------------------------------------------------
# volume
# ---------------------------------------------------------------------------


async def test_volume_state_units_and_state_class(integration: Any) -> None:
    hass = integration.coordinator.hass
    state = hass.states.get(SENSORS["volume"])
    assert state.state == "12"
    assert state.attributes["unit_of_measurement"] == PERCENTAGE
    assert state.attributes["state_class"] == "measurement"


async def test_volume_follows_pushes(integration: Any) -> None:
    hass = integration.coordinator.hass
    integration.tv.volume = 77
    await _refresh(integration)
    assert hass.states.get(SENSORS["volume"]).state == "77"


# ---------------------------------------------------------------------------
# power_state (ENUM)
# ---------------------------------------------------------------------------


async def test_power_state_enum_options_and_device_class(integration: Any) -> None:
    hass = integration.coordinator.hass
    state = hass.states.get(SENSORS["power_state"])
    assert state.state == "Active"
    assert state.attributes["device_class"] == "enum"
    assert state.attributes["options"] == list(POWER_STATE_OPTIONS)


async def test_power_state_foreign_value_folds_to_unknown(integration: Any) -> None:
    """A value outside the option set folds onto "Unknown" (ENUM contract)."""
    hass = integration.coordinator.hass
    integration.tv.power_state = {"state": "Zombie"}
    await _refresh(integration)
    state = hass.states.get(SENSORS["power_state"])
    assert state.state == "Unknown"
    assert state.state in state.attributes["options"]


async def test_power_state_missing_key_folds_to_unknown(integration: Any) -> None:
    hass = integration.coordinator.hass
    integration.tv.power_state = {}
    await _refresh(integration)
    assert hass.states.get(SENSORS["power_state"]).state == "Unknown"


async def test_power_state_screen_off_and_suspend(integration: Any) -> None:
    """Art-standby and suspend are distinct, valid ENUM values."""
    hass = integration.coordinator.hass
    for value in ("Screen Off", "Suspend", "Active Standby"):
        integration.tv.power_state = {"state": value}
        await _refresh(integration)
        assert hass.states.get(SENSORS["power_state"]).state == value


# ---------------------------------------------------------------------------
# current_channel
# ---------------------------------------------------------------------------


async def test_current_channel_number_and_name(integration: Any) -> None:
    hass = integration.coordinator.hass
    integration.tv.current_channel = {
        "channelId": "ch1",
        "channelNumber": "5.1",
        "channelName": "RTL",
    }
    await _refresh(integration)
    assert hass.states.get(SENSORS["current_channel"]).state == "5.1 RTL"


async def test_current_channel_name_only(integration: Any) -> None:
    hass = integration.coordinator.hass
    integration.tv.current_channel = {"channelId": "ch9", "channelName": "Arte"}
    await _refresh(integration)
    assert hass.states.get(SENSORS["current_channel"]).state == "Arte"


async def test_current_channel_not_tuned_is_unknown(integration: Any) -> None:
    hass = integration.coordinator.hass
    assert hass.states.get(SENSORS["current_channel"]).state == "unknown"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


async def test_sensors_unavailable_when_coordinator_fails(
    integration: Any,
) -> None:
    hass = integration.coordinator.hass
    coordinator = integration.coordinator
    coordinator.last_update_success = False
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    for entity_id in SENSORS.values():
        assert hass.states.get(entity_id).state == "unavailable", entity_id

    coordinator.last_update_success = True
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get(SENSORS["volume"]).state == "12"
    assert hass.states.get(SENSORS["current_app"]).state == "YouTube"
