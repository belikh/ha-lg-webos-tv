"""Tests for the remote entity (plan AD-16, AC-23)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from bscpylgtv.buttons import BUTTONS
from homeassistant.components.remote import RemoteEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.bscpylgtv.const import REMOTE_BUTTON_ALIASES

from .conftest import (
    TVSimulator,
    build_mock_config_entry,
    get_entity,
    patch_client_factory,
)

# Re-use the long-lived setup fixture.
from .conftest import integration as _integration  # noqa: F401

REMOTE = "remote.lg_webos_tv_oled55c2_remote"
MAC = "AA:BB:CC:DD:EE:FF"


async def _send(hass: HomeAssistant, command: list[str]) -> None:
    await hass.services.async_call(
        "remote",
        "send_command",
        {"entity_id": REMOTE, "command": command},
        blocking=True,
    )


def _entity(hass: HomeAssistant) -> Any:
    return get_entity(hass, "remote", REMOTE)


async def _setup(
    hass: HomeAssistant, tv: TVSimulator, *, mac: str | None = None
) -> Any:
    from types import SimpleNamespace

    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host, mac=mac)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return SimpleNamespace(entry=entry, tv=tv, client=tv.client)


# ---------------------------------------------------------------------------
# Library buttons (all 77 BUTTONS entries, verbatim)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("button", BUTTONS)
async def test_library_button_sent_verbatim(integration: Any, button: str) -> None:
    """Every bscpylgtv.buttons.BUTTONS name is accepted as-is."""
    hass = integration.coordinator.hass
    await _send(hass, [button])
    integration.tv.client.button.assert_awaited_once_with(button)


@pytest.mark.parametrize(("alias", "expected"), REMOTE_BUTTON_ALIASES.items())
async def test_ha_style_alias_mapped(
    integration: Any, alias: str, expected: str
) -> None:
    hass = integration.coordinator.hass
    await _send(hass, [alias])
    integration.tv.client.button.assert_awaited_once_with(expected)


async def test_button_case_insensitive(integration: Any) -> None:
    hass = integration.coordinator.hass
    await _send(hass, ["home"])
    integration.tv.client.button.assert_awaited_once_with("HOME")


async def test_multiple_commands_in_order(integration: Any) -> None:
    hass = integration.coordinator.hass
    await _send(hass, ["HOME", "ENTER", "BACK"])
    client = integration.tv.client
    assert [c.args[0] for c in client.button.await_args_list] == [
        "HOME",
        "ENTER",
        "BACK",
    ]


async def test_unknown_button_raises(integration: Any) -> None:
    hass = integration.coordinator.hass
    with pytest.raises(HomeAssistantError) as err:
        await _send(hass, ["BOGUS"])
    assert err.value.translation_key == "unknown_button"
    assert err.value.translation_placeholders == {"button": "BOGUS"}
    integration.tv.client.button.assert_not_awaited()


# ---------------------------------------------------------------------------
# Pointer / IME specials
# ---------------------------------------------------------------------------


async def test_click(integration: Any) -> None:
    hass = integration.coordinator.hass
    await _send(hass, ["CLICK"])
    integration.tv.client.click.assert_awaited_once_with()


@pytest.mark.parametrize(
    ("command", "args"),
    [
        ("MOVE:10,-5", (10, -5, 0)),
        ("MOVE:0,0", (0, 0, 0)),
        ("MOVE:3,4,1", (3, 4, 1)),
        ("MOVE:-12,7", (-12, 7, 0)),
    ],
)
async def test_move(integration: Any, command: str, args: tuple[int, ...]) -> None:
    hass = integration.coordinator.hass
    await _send(hass, [command])
    integration.tv.client.move.assert_awaited_once_with(*args)


@pytest.mark.parametrize("command", ["MOVE:1", "MOVE:a,b", "MOVE:1,2,3,4"])
async def test_move_invalid_raises(integration: Any, command: str) -> None:
    hass = integration.coordinator.hass
    with pytest.raises(HomeAssistantError) as err:
        await _send(hass, [command])
    assert err.value.translation_key == "unknown_button"
    integration.tv.client.move.assert_not_awaited()


@pytest.mark.parametrize(
    ("command", "args"),
    [("SCROLL:0,-3", (0, -3)), ("SCROLL:-5,10", (-5, 10))],
)
async def test_scroll(integration: Any, command: str, args: tuple[int, ...]) -> None:
    hass = integration.coordinator.hass
    await _send(hass, [command])
    integration.tv.client.scroll.assert_awaited_once_with(*args)


@pytest.mark.parametrize("command", ["SCROLL:1", "SCROLL:1,2,3", "SCROLL:x,y"])
async def test_scroll_invalid_raises(integration: Any, command: str) -> None:
    hass = integration.coordinator.hass
    with pytest.raises(HomeAssistantError) as err:
        await _send(hass, [command])
    assert err.value.translation_key == "unknown_button"
    integration.tv.client.scroll.assert_not_awaited()


@pytest.mark.parametrize(
    ("command", "text"),
    [("TEXT:hello", "hello"), ("TEXT:HeLLo World", "HeLLo World"), ("TEXT:", None)],
)
async def test_text(integration: Any, command: str, text: str | None) -> None:
    """Case is preserved from the raw command; empty text is rejected."""
    hass = integration.coordinator.hass
    if text is None:
        with pytest.raises(HomeAssistantError) as err:
            await _send(hass, [command])
        assert err.value.translation_key == "unknown_button"
        integration.tv.client.insert_text.assert_not_awaited()
        return
    await _send(hass, [command])
    integration.tv.client.insert_text.assert_awaited_once_with(text)


# ---------------------------------------------------------------------------
# current_activity / supported_features
# ---------------------------------------------------------------------------


async def test_current_activity_from_app_title(integration: Any) -> None:
    hass = integration.coordinator.hass
    assert _entity(hass).current_activity == "YouTube"
    assert hass.states.get(REMOTE).attributes["current_activity"] == "YouTube"


async def test_current_activity_from_input_label(integration: Any) -> None:
    hass = integration.coordinator.hass
    integration.tv.current_appId = "com.webos.app.hdmi1"
    integration.tv.push_update()
    await hass.async_block_till_done()
    assert _entity(hass).current_activity == "HDMI 1"


async def test_current_activity_live_tv(integration: Any) -> None:
    hass = integration.coordinator.hass
    integration.tv.current_appId = "com.webos.app.livetv"
    integration.tv.push_update()
    await hass.async_block_till_done()
    assert _entity(hass).current_activity == "Live TV"


async def test_current_activity_unknown_app_id_raw(integration: Any) -> None:
    hass = integration.coordinator.hass
    integration.tv.current_appId = "com.webos.app.mystery"
    integration.tv.push_update()
    await hass.async_block_till_done()
    assert _entity(hass).current_activity == "com.webos.app.mystery"


async def test_current_activity_none_without_app(integration: Any) -> None:
    hass = integration.coordinator.hass
    integration.tv.current_appId = None
    integration.tv.push_update()
    await hass.async_block_till_done()
    assert _entity(hass).current_activity is None


async def test_supported_features_activity_only(integration: Any) -> None:
    hass = integration.coordinator.hass
    assert _entity(hass).supported_features == RemoteEntityFeature.ACTIVITY


# ---------------------------------------------------------------------------
# turn_on / turn_off (actual flow: SSAP screen-wake while on; WOL when off)
# ---------------------------------------------------------------------------


async def test_turn_on_screen_off_wakes_screen_over_ssap(integration: Any) -> None:
    """Art-standby (on, screen off): SSAP screen wake, never WOL."""
    hass = integration.coordinator.hass
    integration.tv.power_state = {"state": "Screen Off"}
    integration.tv.push_update()
    await hass.async_block_till_done()
    with patch(
        "custom_components.bscpylgtv.remote._async_send_wol", new_callable=AsyncMock
    ) as wol:
        await hass.services.async_call(
            "remote", "turn_on", {"entity_id": REMOTE}, blocking=True
        )
    integration.tv.client.turn_screen_on.assert_awaited_once()
    wol.assert_not_awaited()


async def test_turn_on_screen_on_is_a_noop(integration: Any) -> None:
    hass = integration.coordinator.hass
    with patch(
        "custom_components.bscpylgtv.remote._async_send_wol", new_callable=AsyncMock
    ) as wol:
        await hass.services.async_call(
            "remote", "turn_on", {"entity_id": REMOTE}, blocking=True
        )
    integration.tv.client.turn_screen_on.assert_not_awaited()
    wol.assert_not_awaited()


async def test_turn_on_power_off_sends_wol(
    tv: TVSimulator, hass: HomeAssistant
) -> None:
    """A fully powered-off TV is woken with the WOL magic packet."""
    tv.power_state = {"state": "Power Off"}
    await _setup(hass, tv, mac=MAC)
    with patch(
        "custom_components.bscpylgtv.remote._async_send_wol",
        new_callable=AsyncMock,
    ) as wol:
        await hass.services.async_call(
            "remote", "turn_on", {"entity_id": REMOTE}, blocking=True
        )
    wol.assert_awaited_once_with(hass, MAC)
    tv.client.turn_screen_on.assert_not_awaited()


async def test_turn_on_power_off_without_mac_warns(
    tv: TVSimulator, hass: HomeAssistant, caplog: Any
) -> None:
    # A non-MAC device_id: the MAC self-heal must not repair the entry.
    tv.software_info = {**tv.software_info, "device_id": "webos-device"}
    tv.power_state = {"state": "Power Off"}
    await _setup(hass, tv, mac=None)
    with patch(
        "custom_components.bscpylgtv.remote._async_send_wol",
        new_callable=AsyncMock,
    ) as wol:
        await hass.services.async_call(
            "remote", "turn_on", {"entity_id": REMOTE}, blocking=True
        )
    wol.assert_not_awaited()
    assert "no MAC address configured" in caplog.text


async def test_turn_off_is_screen_off(integration: Any) -> None:
    hass = integration.coordinator.hass
    await hass.services.async_call(
        "remote", "turn_off", {"entity_id": REMOTE}, blocking=True
    )
    integration.tv.client.turn_screen_off.assert_awaited_once()


async def test_is_on_mirrors_client(integration: Any) -> None:
    hass = integration.coordinator.hass
    assert hass.states.get(REMOTE).state == "on"
    integration.tv.power_state = {"state": "Power Off"}
    integration.tv.push_update()
    await hass.async_block_till_done()
    assert hass.states.get(REMOTE).state == "off"
