"""Tests for the select platform (plan AD-13, AC-9/10)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from bscpylgtv.exceptions import PyLGTVCmdError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.bscpylgtv.const import (
    PICTURE_MODES_FALLBACK,
    SOUND_OUTPUTS,
)

from .conftest import get_entity
from .conftest import integration as _integration  # noqa: F401

SELECTS = {
    "picture_mode": "select.lg_webos_tv_oled55c2_picture_mode",
    "sound_output": "select.lg_webos_tv_oled55c2_sound_output",
    "channel": "select.lg_webos_tv_oled55c2_channel",
}


async def _select(hass: HomeAssistant, entity_id: str, option: str) -> None:
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": option},
        blocking=True,
    )


def _entity(hass: HomeAssistant, key: str) -> Any:
    return get_entity(hass, "select", SELECTS[key])


async def _refresh(integration: Any) -> None:
    """Push an update and let the scheduled one-shot reads land."""
    hass = integration.coordinator.hass
    integration.tv.push_update()
    await hass.async_block_till_done()
    await hass.async_block_till_done()


# ---------------------------------------------------------------------------
# picture_mode (AC-9)
# ---------------------------------------------------------------------------


async def test_picture_mode_fallback_before_read(integration: Any) -> None:
    """Before any live read: the curated fallback (never the v1 list)."""
    hass = integration.coordinator.hass
    state = hass.states.get(SELECTS["picture_mode"])
    assert state.attributes["options"] == list(PICTURE_MODES_FALLBACK)
    assert "aps" not in state.attributes["options"]
    assert "technicolorExpert" not in state.attributes["options"]


async def test_picture_mode_live_enum_list(integration: Any) -> None:
    """A C2-style enum list replaces the fallback."""
    hass = integration.coordinator.hass
    integration.tv.client.get_system_settings = AsyncMock(  # type: ignore[method-assign]
        return_value={"settings": {"pictureMode": ["normal", "vivid", "expert1"]}}
    )
    await _refresh(integration)
    state = hass.states.get(SELECTS["picture_mode"])
    assert state.attributes["options"] == ["normal", "vivid", "expert1"]


async def test_picture_mode_string_current(integration: Any) -> None:
    """A string answer becomes the current mode over the fallback list."""
    hass = integration.coordinator.hass
    integration.tv.client.get_system_settings = AsyncMock(  # type: ignore[method-assign]
        return_value={"settings": {"pictureMode": "expert2"}}
    )
    await _refresh(integration)
    state = hass.states.get(SELECTS["picture_mode"])
    assert state.attributes["options"] == list(PICTURE_MODES_FALLBACK)
    assert state.state == "expert2"


async def test_picture_mode_unknown_current_appended(integration: Any) -> None:
    """An unknown current mode stays visible (appended option)."""
    hass = integration.coordinator.hass
    integration.tv.client.get_system_settings = AsyncMock(  # type: ignore[method-assign]
        return_value={"settings": {"pictureMode": "vendorSpecialMode"}}
    )
    await _refresh(integration)
    state = hass.states.get(SELECTS["picture_mode"])
    assert state.state == "vendorSpecialMode"
    assert state.attributes["options"][-1] == "vendorSpecialMode"


async def test_picture_mode_read_failure_keeps_fallback(integration: Any) -> None:
    """A rejected read keeps the curated fallback (R-3)."""
    hass = integration.coordinator.hass
    integration.tv.client.get_system_settings = AsyncMock(  # type: ignore[method-assign]
        side_effect=PyLGTVCmdError("read rejected")
    )
    await _refresh(integration)
    state = hass.states.get(SELECTS["picture_mode"])
    assert state.attributes["options"] == list(PICTURE_MODES_FALLBACK)


async def test_picture_mode_select_option(integration: Any) -> None:
    """Writes go through the Luna set_settings path and mirror back."""
    hass = integration.coordinator.hass
    await _select(hass, SELECTS["picture_mode"], "cinema")
    integration.tv.client.set_settings.assert_awaited_once_with(
        "picture", {"pictureMode": "cinema"}
    )
    assert hass.states.get(SELECTS["picture_mode"]).state == "cinema"


async def test_picture_mode_restores_after_reload(integration: Any) -> None:
    """The last written mode survives a reload (RestoreEntity).

    Regression: models that refuse every pictureMode read (verified on a
    CX OLED) kept falling back to unknown after every HA restart, even
    after the user had set a mode from HA.
    """
    hass = integration.coordinator.hass
    entry = integration.entry
    await _select(hass, SELECTS["picture_mode"], "cinema")
    assert hass.states.get(SELECTS["picture_mode"]).state == "cinema"

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    state = hass.states.get(SELECTS["picture_mode"])
    assert state is not None
    assert state.state == "cinema", "restored value lost after reload"


async def test_picture_mode_pushed_current_wins(integration: Any) -> None:
    """A subscription push (if any) overrides the cached current."""
    hass = integration.coordinator.hass
    integration.tv.picture_settings = {
        **integration.tv.picture_settings,
        "pictureMode": "game",
    }
    integration.tv.push_update()
    await hass.async_block_till_done()
    assert hass.states.get(SELECTS["picture_mode"]).state == "game"


async def test_picture_mode_oneshot_per_client(integration: Any) -> None:
    """The enum read runs once per client, refires after a swap."""
    hass = integration.coordinator.hass
    integration.tv.push_update()
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    first = integration.tv.client
    assert first.get_system_settings.await_count == 1

    integration.tv.push_update()
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    assert first.get_system_settings.await_count == 1  # no re-read

    integration.tv.disconnect_all()
    await integration.coordinator.async_refresh()
    await hass.async_block_till_done()
    second = integration.tv.client
    assert second is not first
    integration.tv.push_update()
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    assert second.get_system_settings.await_count == 1


# ---------------------------------------------------------------------------
# sound_output
# ---------------------------------------------------------------------------


async def test_sound_output_options_and_current(integration: Any) -> None:
    hass = integration.coordinator.hass
    state = hass.states.get(SELECTS["sound_output"])
    assert state.state == "tv_speaker"
    assert state.attributes["options"] == list(SOUND_OUTPUTS)


async def test_sound_output_foreign_current_unioned(integration: Any) -> None:
    """A value outside the curated list is unioned in."""
    hass = integration.coordinator.hass
    integration.tv.sound_output = "wisa_speaker_pro"
    integration.tv.push_update()
    await hass.async_block_till_done()
    state = hass.states.get(SELECTS["sound_output"])
    assert state.state == "wisa_speaker_pro"
    assert state.attributes["options"] == [*SOUND_OUTPUTS, "wisa_speaker_pro"]


async def test_sound_output_select(integration: Any) -> None:
    """Writes use change_sound_output (there is no set_sound_output)."""
    hass = integration.coordinator.hass
    await _select(hass, SELECTS["sound_output"], "external_arc")
    integration.tv.client.change_sound_output.assert_awaited_once_with("external_arc")


# ---------------------------------------------------------------------------
# channel (AC-10, R-5)
# ---------------------------------------------------------------------------


async def test_channel_options_from_lineup(integration: Any) -> None:
    hass = integration.coordinator.hass
    integration.tv.push_update()
    await hass.async_block_till_done()
    state = hass.states.get(SELECTS["channel"])
    assert state.attributes["options"] == ["5.1 RTL", "10 ZDF HD", "20  Arte"]


async def test_channel_current_from_channel_id(integration: Any) -> None:
    hass = integration.coordinator.hass
    integration.tv.current_channel = {
        "channelId": "ch2",
        "channelNumber": "10",
        "channelName": "ZDF HD",
    }
    integration.tv.push_update()
    await hass.async_block_till_done()
    assert hass.states.get(SELECTS["channel"]).state == "10 ZDF HD"


async def test_channel_select_tunes_by_id(integration: Any) -> None:
    hass = integration.coordinator.hass
    integration.tv.push_update()
    await hass.async_block_till_done()
    await _select(hass, SELECTS["channel"], "5.1 RTL")
    integration.tv.client.set_channel.assert_awaited_once_with("ch1")


async def test_channel_bad_option_raises(integration: Any) -> None:
    """An unresolvable option raises the entity's channel_not_found guard.

    HA's select platform validates the option against ``options`` before
    dispatching to the entity (raising its own ``not_valid_option``), so
    the entity-level guard (select.py) is reached via a direct entity
    call — e.g. a stale option still shown by a dashboard.
    """
    hass = integration.coordinator.hass
    integration.tv.push_update()
    await hass.async_block_till_done()
    with pytest.raises(HomeAssistantError) as err:
        await _entity(hass, "channel").async_select_option("999.9 Nonexistent")
    assert err.value.translation_key == "channel_not_found"
    assert err.value.translation_placeholders == {"channel": "999.9 Nonexistent"}
    integration.tv.client.set_channel.assert_not_awaited()


async def test_channel_bad_option_via_service_rejected(integration: Any) -> None:
    """The service path rejects an option outside the lineup outright."""
    hass = integration.coordinator.hass
    integration.tv.push_update()
    await hass.async_block_till_done()
    with pytest.raises(HomeAssistantError):
        await _select(hass, SELECTS["channel"], "999.9 Nonexistent")
    integration.tv.client.set_channel.assert_not_awaited()


async def test_channel_empty_lineup_stays_alive(integration: Any) -> None:
    """No lineup yet: entity exists, options empty, current unknown."""
    hass = integration.coordinator.hass
    integration.tv.channels = None
    integration.tv.push_update()
    await hass.async_block_till_done()
    state = hass.states.get(SELECTS["channel"])
    assert state is not None
    assert state.attributes["options"] == []
    assert state.state == "unknown"


async def test_channel_diff_guard_no_rebuild_on_same_list(
    integration: Any,
) -> None:
    """R-5: an identical re-push reuses the cached option list."""
    hass = integration.coordinator.hass
    entity = _entity(hass, "channel")
    integration.tv.push_update()
    await hass.async_block_till_done()
    first = entity.options
    assert entity.options is first  # cached, same object

    # Same lineup re-pushed: still the same cached list object.
    integration.tv.push_update()
    await hass.async_block_till_done()
    assert entity.options is first


async def test_channel_diff_guard_rebuilds_on_change(integration: Any) -> None:
    """A changed lineup (length or boundary) rebuilds the options."""
    hass = integration.coordinator.hass
    entity = _entity(hass, "channel")
    integration.tv.push_update()
    await hass.async_block_till_done()
    first = entity.options

    integration.tv.channels = [
        *integration.tv.channels,
        {
            "channelId": "ch4",
            "channelNumber": "30",
            "channelName": "New",
        },
    ]
    integration.tv.push_update()
    await hass.async_block_till_done()
    rebuilt = entity.options
    assert rebuilt is not first
    assert "30 New" in rebuilt


async def test_channel_large_lineup_handled(integration: Any) -> None:
    """A 1200-channel lineup builds correct options (R-5 sanity)."""
    hass = integration.coordinator.hass
    integration.tv.channels = [
        {"channelId": f"ch{i}", "channelNumber": str(i), "channelName": f"Chan {i}"}
        for i in range(1200)
    ]
    integration.tv.push_update()
    await hass.async_block_till_done()
    state = hass.states.get(SELECTS["channel"])
    assert len(state.attributes["options"]) == 1200


async def test_channel_malformed_entries_skipped(integration: Any) -> None:
    """Channels without number/name or id are skipped, not guessed."""
    hass = integration.coordinator.hass
    integration.tv.channels = [
        {"channelId": "ch1", "channelNumber": "5.1"},  # name missing → number only
        {"channelNumber": "7", "channelName": "NoId"},  # id missing → skipped
        {"channelName": "Neither"},  # neither → skipped
    ]
    integration.tv.push_update()
    await hass.async_block_till_done()
    state = hass.states.get(SELECTS["channel"])
    assert state.attributes["options"] == ["5.1"]


async def test_select_registry_shape(integration: Any) -> None:
    """Three selects, enabled, no category."""
    hass = integration.coordinator.hass
    registry = er.async_get(hass)
    uid = integration.entry.unique_id
    selects = {
        e.unique_id.removeprefix(f"{uid}_")
        for e in registry.entities.values()
        if e.domain == "select" and e.unique_id and e.unique_id.startswith(uid)
    }
    assert selects == {"picture_mode", "sound_output", "channel"}
    for e in registry.entities.values():
        if e.domain == "select":
            assert e.disabled_by is None
            assert e.entity_category is None
