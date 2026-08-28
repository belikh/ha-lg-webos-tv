"""Tests for the number platform (plan AD-12, AC-8)."""

from __future__ import annotations

from typing import Any

import pytest
from bscpylgtv.exceptions import PyLGTVCmdError
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.bscpylgtv.const import PICTURE_NUMBER_RANGES

from .conftest import integration as _integration  # noqa: F401

EXPECTED_KEYS = {
    "backlight": (0, 100),
    "contrast": (0, 100),
    "brightness": (0, 100),
    "color": (0, 100),
    "sharpness": (0, 50),
    "color_temperature": (-50, 50),
}


def _numbers(hass: HomeAssistant, uid: str) -> dict[str, Any]:
    registry = er.async_get(hass)
    return {
        entry.unique_id.removeprefix(f"{uid}_"): entry
        for entry in registry.entities.values()
        if entry.domain == "number"
        and entry.unique_id
        and entry.unique_id.startswith(uid)
    }


async def _enable_all(hass: HomeAssistant, integration: Any) -> dict[str, str]:
    entries = _numbers(hass, integration.entry.unique_id)
    for reg in entries.values():
        er.async_get(hass).async_update_entity(reg.entity_id, disabled_by=None)
    assert await hass.config_entries.async_reload(integration.entry.entry_id)
    await hass.async_block_till_done()
    # The reload built a new coordinator + client: re-sync the namespace.
    integration.coordinator = integration.entry.runtime_data
    integration.client = integration.tv.client
    return {key: reg.entity_id for key, reg in entries.items()}


async def _set(hass: HomeAssistant, entity_id: str, value: float) -> None:
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True
    )


async def test_number_registry_shape(integration: Any) -> None:
    """Six sliders, CONFIG category, disabled by default, exact ranges."""
    hass = integration.coordinator.hass
    numbers = _numbers(hass, integration.entry.unique_id)
    assert set(numbers) == set(EXPECTED_KEYS)
    for _key, reg in numbers.items():
        assert reg.disabled_by == er.RegistryEntryDisabler.INTEGRATION
        assert reg.entity_category is EntityCategory.CONFIG
    # Ranges come from the frozen C2 map and match the plan.
    assert PICTURE_NUMBER_RANGES == {
        "backlight": (0, 100),
        "contrast": (0, 100),
        "brightness": (0, 100),
        "color": (0, 100),
        "sharpness": (0, 50),
        "colorTemperature": (-50, 50),
    }


async def test_number_state_attributes(integration: Any) -> None:
    """Enabled sliders expose min/max/step/mode in their states."""
    hass = integration.coordinator.hass
    ids = await _enable_all(hass, integration)
    for key, (minimum, maximum) in EXPECTED_KEYS.items():
        state = hass.states.get(ids[key])
        assert state.attributes["min"] == minimum
        assert state.attributes["max"] == maximum
        assert state.attributes["step"] == 1.0
        assert state.attributes["mode"] == "slider"


async def test_pushed_keys_read_from_picture_settings(integration: Any) -> None:
    """backlight/contrast/brightness/color come from the pushed state."""
    hass = integration.coordinator.hass
    ids = await _enable_all(hass, integration)
    assert hass.states.get(ids["backlight"]).state == "50.0"
    tv = integration.tv
    tv.picture_settings = {**tv.picture_settings, "contrast": 95}
    tv.push_update()
    await hass.async_block_till_done()
    assert hass.states.get(ids["contrast"]).state == "95.0"


async def test_string_values_coerced(integration: Any) -> None:
    """webOS answers carry strings ("10"): still rendered as numbers."""
    hass = integration.coordinator.hass
    ids = await _enable_all(hass, integration)
    assert hass.states.get(ids["sharpness"]).state == "10.0"


async def test_set_value_writes_luna_and_mirrors(integration: Any) -> None:
    """Writes go through set_settings("picture", {key: int})."""
    hass = integration.coordinator.hass
    ids = await _enable_all(hass, integration)
    await _set(hass, ids["backlight"], 30)
    integration.tv.client.set_settings.assert_awaited_once_with(
        "picture", {"backlight": 30}
    )
    # Optimistic mirror: no push confirms Luna writes.
    assert hass.states.get(ids["backlight"]).state == "30.0"


async def test_stale_echo_does_not_clobber_optimistic(
    integration: Any,
) -> None:
    """An unchanged push is a stale echo and keeps the written value."""
    hass = integration.coordinator.hass
    ids = await _enable_all(hass, integration)
    tv = integration.tv
    tv.picture_settings = {**tv.picture_settings, "sharpness": "10"}
    tv.push_update()
    await hass.async_block_till_done()

    await _set(hass, ids["sharpness"], 20)
    # The TV re-pushes its old subscription state (Luna write invisible).
    tv.push_update()
    await hass.async_block_till_done()
    assert hass.states.get(ids["sharpness"]).state == "20.0"


async def test_changed_push_wins(integration: Any) -> None:
    """A genuinely changed push overrides the optimistic value."""
    hass = integration.coordinator.hass
    ids = await _enable_all(hass, integration)
    tv = integration.tv
    # Prime the staleness baseline with the current push, then write.
    tv.push_update()
    await hass.async_block_till_done()
    await _set(hass, ids["sharpness"], 20)
    tv.picture_settings = {**tv.picture_settings, "sharpness": "25"}
    tv.push_update()
    await hass.async_block_till_done()
    assert hass.states.get(ids["sharpness"]).state == "25.0"


async def test_oneshot_read_once_per_client(integration: Any) -> None:
    """sharpness/colorTemperature read once per client instance."""
    hass = integration.coordinator.hass
    ids = await _enable_all(hass, integration)
    tv = integration.tv
    first = tv.client
    tv.push_update()
    await hass.async_block_till_done()
    read_keys_first = [c.args[0] for c in first.get_picture_settings.await_args_list]
    assert read_keys_first == [["sharpness"], ["colorTemperature"]]

    tv.push_update()  # second push, same client: no re-read
    await hass.async_block_till_done()
    assert first.get_picture_settings.await_count == 2  # still the two above

    # Client swap (reconnect): the fresh client reads again.
    tv.disconnect_all()
    await integration.coordinator.async_refresh()
    await hass.async_block_till_done()
    second = tv.client
    assert second is not first
    tv.picture_settings = {**tv.picture_settings, "sharpness": "12"}
    tv.push_update()
    await hass.async_block_till_done()
    read_keys_second = [c.args[0] for c in second.get_picture_settings.await_args_list]
    assert read_keys_second == [["sharpness"], ["colorTemperature"]]
    assert hass.states.get(ids["sharpness"]).state == "12.0"


async def test_oneshot_read_failure_keeps_last(integration: Any) -> None:
    """A rejected one-shot read keeps the last value (R-3/R-9)."""
    from unittest.mock import AsyncMock

    hass = integration.coordinator.hass
    ids = await _enable_all(hass, integration)
    tv = integration.tv
    # Prime the baseline, then write optimistically.
    tv.push_update()
    await hass.async_block_till_done()
    await _set(hass, ids["color_temperature"], -10)
    tv.client.get_picture_settings = AsyncMock(  # type: ignore[method-assign]
        side_effect=PyLGTVCmdError("read rejected")
    )
    tv.push_update()
    await hass.async_block_till_done()
    assert hass.states.get(ids["color_temperature"]).state == "-10.0"


async def test_write_blocked_when_device_off(integration: Any) -> None:
    hass = integration.coordinator.hass
    ids = await _enable_all(hass, integration)
    integration.tv.power_state = {"state": "Power Off"}
    integration.tv.push_update()
    await hass.async_block_till_done()
    with pytest.raises(HomeAssistantError) as err:
        await _set(hass, ids["backlight"], 30)
    assert err.value.translation_key == "device_off"
    integration.tv.client.set_settings.assert_not_awaited()
