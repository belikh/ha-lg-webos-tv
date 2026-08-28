"""Tests for the button platform (plan AD-9/AD-11, AC-23)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .conftest import FAKE_JPEG

# Re-use the long-lived setup fixture (patch stays active so the entry can
# be reloaded after enabling disabled-by-default entities).
from .conftest import integration as _integration  # noqa: F401


def _buttons(hass: HomeAssistant, uid: str) -> dict[str, Any]:
    registry = er.async_get(hass)
    return {
        entry.unique_id.removeprefix(f"{uid}_"): entry
        for entry in registry.entities.values()
        if entry.domain == "button"
        and entry.unique_id
        and entry.unique_id.startswith(uid)
    }


async def _press(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )


async def _enable(hass: HomeAssistant, entity_id: str, entry: Any) -> None:
    """Enable a disabled entity and reload the entry to add it back."""
    er.async_get(hass).async_update_entity(entity_id, disabled_by=None)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id) is not None


async def test_button_registry_shape(integration: Any) -> None:
    """Four buttons; reboot CONFIG + disabled; the rest enabled."""
    hass = integration.coordinator.hass
    buttons = _buttons(hass, integration.entry.unique_id)
    assert set(buttons) == {
        "turn_screen_off",
        "turn_screen_on",
        "screenshot",
        "reboot",
    }
    reboot = buttons["reboot"]
    assert reboot.disabled_by == er.RegistryEntryDisabler.INTEGRATION
    assert reboot.entity_category is EntityCategory.CONFIG
    for key in ("turn_screen_off", "turn_screen_on", "screenshot"):
        assert buttons[key].disabled_by is None
        assert buttons[key].entity_category is None


async def test_press_screen_buttons(integration: Any) -> None:
    hass = integration.coordinator.hass
    buttons = _buttons(hass, integration.entry.unique_id)
    await _press(hass, buttons["turn_screen_off"].entity_id)
    await _press(hass, buttons["turn_screen_on"].entity_id)
    integration.client.turn_screen_off.assert_awaited_once()
    integration.client.turn_screen_on.assert_awaited_once()


async def test_press_reboot(integration: Any) -> None:
    hass = integration.coordinator.hass
    registry_entry = _buttons(hass, integration.entry.unique_id)["reboot"]
    await _enable(hass, registry_entry.entity_id, integration.entry)
    await _press(hass, registry_entry.entity_id)
    integration.tv.client.reboot.assert_awaited_once()


async def test_press_screenshot_writes_jpeg(integration: Any) -> None:
    hass = integration.coordinator.hass
    registry_entry = _buttons(hass, integration.entry.unique_id)["screenshot"]
    await _press(hass, registry_entry.entity_id)
    path = Path(hass.config.path("www", f"bscpylgtv_{integration.entry.unique_id}.jpg"))
    assert await hass.async_add_executor_job(path.is_file)
    data = await hass.async_add_executor_job(path.read_bytes)
    assert data[:2] == b"\xff\xd8"  # JPEG magic
    assert data == FAKE_JPEG


async def test_press_screenshot_write_failure(integration: Any) -> None:
    hass = integration.coordinator.hass
    registry_entry = _buttons(hass, integration.entry.unique_id)["screenshot"]
    with (
        patch(
            "custom_components.bscpylgtv.button._write_screenshot",
            side_effect=OSError("disk full"),
        ),
        pytest.raises(HomeAssistantError) as err,
    ):
        await _press(hass, registry_entry.entity_id)
    assert err.value.translation_key == "screenshot_write_failed"


async def test_press_blocked_when_device_off(integration: Any) -> None:
    hass = integration.coordinator.hass
    integration.tv.power_state = {"state": "Power Off"}
    integration.tv.push_update()
    await hass.async_block_till_done()
    registry_entry = _buttons(hass, integration.entry.unique_id)["turn_screen_off"]
    with pytest.raises(HomeAssistantError) as err:
        await _press(hass, registry_entry.entity_id)
    assert err.value.translation_key == "device_off"
    integration.client.turn_screen_off.assert_not_awaited()
