"""Tests for the switch platform (plan §3.2/§8.4, AC-23)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from bscpylgtv.exceptions import PyLGTVCmdError
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

# Re-use the long-lived setup fixture (patch stays active for reloads).
from .conftest import integration as _integration  # noqa: F401

SWITCHES = {
    "tpc": "switch.lg_webos_tv_oled55c2_tpc",
    "gsr": "switch.lg_webos_tv_oled55c2_gsr",
}


def _registry_entries(hass: HomeAssistant, uid: str) -> dict[str, Any]:
    registry = er.async_get(hass)
    return {
        entry.unique_id.removeprefix(f"{uid}_"): entry
        for entry in registry.entities.values()
        if entry.domain == "switch"
        and entry.unique_id
        and entry.unique_id.startswith(uid)
    }


async def _enable_all(hass: HomeAssistant, integration: Any) -> None:
    """Enable both disabled-by-default switches and reload the entry."""
    for reg in _registry_entries(hass, integration.entry.unique_id).values():
        er.async_get(hass).async_update_entity(reg.entity_id, disabled_by=None)
    assert await hass.config_entries.async_reload(integration.entry.entry_id)
    await hass.async_block_till_done()
    # The reload built a new coordinator + client: re-sync the namespace.
    integration.coordinator = integration.entry.runtime_data
    integration.client = integration.tv.client


async def _turn(hass: HomeAssistant, entity_id: str, service: str) -> None:
    await hass.services.async_call(
        "switch", service, {"entity_id": entity_id}, blocking=True
    )


async def test_switch_registry_shape(integration: Any) -> None:
    """Exactly tpc + gsr: CONFIG category, disabled by default."""
    hass = integration.coordinator.hass
    entries = _registry_entries(hass, integration.entry.unique_id)
    assert set(entries) == {"tpc", "gsr"}
    for key, reg in entries.items():
        assert reg.entity_category is EntityCategory.CONFIG, key
        assert reg.disabled_by == er.RegistryEntryDisabler.INTEGRATION, key


async def test_switch_state_unknown_before_first_write(integration: Any) -> None:
    """No readable webOS key: the state is unknown until a write lands."""
    hass = integration.coordinator.hass
    await _enable_all(hass, integration)
    for entity_id in SWITCHES.values():
        assert hass.states.get(entity_id).state == "unknown", entity_id
    integration.tv.client.enable_tpc_or_gsr.assert_not_awaited()


async def test_turn_on_writes_algo_and_mirrors(integration: Any) -> None:
    hass = integration.coordinator.hass
    await _enable_all(hass, integration)
    await _turn(hass, SWITCHES["tpc"], "turn_on")
    integration.tv.client.enable_tpc_or_gsr.assert_awaited_once_with("tpc", True)
    assert hass.states.get(SWITCHES["tpc"]).state == "on"
    assert hass.states.get(SWITCHES["gsr"]).state == "unknown"


async def test_turn_off_writes_algo_and_mirrors(integration: Any) -> None:
    hass = integration.coordinator.hass
    await _enable_all(hass, integration)
    await _turn(hass, SWITCHES["gsr"], "turn_off")
    integration.tv.client.enable_tpc_or_gsr.assert_awaited_once_with("gsr", False)
    assert hass.states.get(SWITCHES["gsr"]).state == "off"
    assert hass.states.get(SWITCHES["tpc"]).state == "unknown"


async def test_switch_blocked_when_device_off(integration: Any) -> None:
    """The device-off guard applies to the Luna writer."""
    hass = integration.coordinator.hass
    await _enable_all(hass, integration)
    integration.tv.power_state = {"state": "Power Off"}
    integration.tv.push_update()
    await hass.async_block_till_done()
    with pytest.raises(HomeAssistantError) as err:
        await _turn(hass, SWITCHES["tpc"], "turn_on")
    assert err.value.translation_key == "device_off"
    integration.tv.client.enable_tpc_or_gsr.assert_not_awaited()


async def test_switch_write_failure_translates(integration: Any) -> None:
    """A persistent Luna failure surfaces as communication_error.

    The link probe still passes, so the cmd-wrapper's recovery pass is a
    no-op and the retry fails against the same client.
    """
    hass = integration.coordinator.hass
    await _enable_all(hass, integration)
    integration.tv.client.enable_tpc_or_gsr = AsyncMock(  # type: ignore[method-assign]
        side_effect=PyLGTVCmdError("luna refused")
    )
    with pytest.raises(HomeAssistantError) as err:
        await _turn(hass, SWITCHES["gsr"], "turn_on")
    assert err.value.translation_key == "communication_error"
    assert hass.states.get(SWITCHES["gsr"]).state == "unknown"
