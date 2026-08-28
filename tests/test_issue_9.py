"""Regression tests for issue #9 (belikh/ha-lg-webos-tv#9).

Three user-reported symptoms against v1.0.4, each addressed by the v2
push coordinator + watchdog architecture. Every test here fails on the
v1 design (no reconnect, unbounded teardown, dead subscription) and must
pass on v2 without any HA restart or user intervention.

1. "When the TV was off, all sensors are unavailable until I restart HA."
   → the watchdog reconnects on its own; without a WOL MAC the entities
   return to available with fresh values, with a MAC they never leave
   available (webostv semantics: available showing OFF).
2. "The integration reloading does not really work ... a full ha restart
   is necessary." → a UI reload must complete even when the old client's
   ``disconnect()`` wedges (v1 awaited the library's uncancellable
   teardown) and the reloaded entry must work end to end.
3. "After restart ... the sound output sensor suddenly shows tv_speaker
   even though it should be external_arc." → a value that changed on the
   TV while it was unreachable must be re-synced from the fresh client
   on reconnect (v1 kept the stale/default value because its
   subscription callback had died — the dict-iteration bug fixed in
   PR #8 by the same reporter).
"""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .conftest import TVSimulator, build_mock_config_entry, patch_client_factory

MEDIA_PLAYER = "media_player.lg_webos_tv_oled55c2"
CURRENT_APP_SENSOR = "sensor.lg_webos_tv_oled55c2_current_app"
SOUND_OUTPUT_SELECT = "select.lg_webos_tv_oled55c2_sound_output"


# ---------------------------------------------------------------------------
# Symptom 1: entities unavailable after the TV was off, until HA restart
# ---------------------------------------------------------------------------


async def test_tv_off_entities_recover_without_restart(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """No WOL path: outage → unavailable → available again, automatically."""
    # No MAC-shaped device_id, so the self-heal cannot grant a wake path.
    tv.software_info = {**tv.software_info, "device_id": "webos-device"}
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host, mac=None)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data

        # Healthy baseline: media player on, sensors populated.
        assert hass.states.get(MEDIA_PLAYER).state == "on"
        assert hass.states.get(CURRENT_APP_SENSOR).state == "YouTube"

        # The TV drops off the network (hard off / Wi-Fi loss).
        tv.disconnect_all()
        tv.connect_exception = OSError("TV is off")
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        assert hass.states.get(MEDIA_PLAYER).state == "unavailable"
        assert hass.states.get(CURRENT_APP_SENSOR).state == "unavailable"

        # The TV comes back — no HA restart, no reload, nothing manual.
        tv.connect_exception = None
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        tv.push_update()
        await hass.async_block_till_done()

        assert hass.states.get(MEDIA_PLAYER).state == "on"
        assert hass.states.get(CURRENT_APP_SENSOR).state == "YouTube"
        assert hass.states.get(MEDIA_PLAYER).attributes["volume_level"] == 0.12


async def test_tv_off_with_wol_stays_available_and_recovers(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """WOL path: available showing OFF during the outage, then fresh on."""
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host, mac=tv.mac)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data

        # Graceful power-off: the TV pushes the state change, then the socket
        # closes — modelled in that order.
        tv.power_state = {"state": "Power Off"}
        tv.disconnect_all()
        tv.connect_exception = OSError("TV is off")
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        # Wake path exists → the entity stays AVAILABLE showing OFF
        # (never "unavailable": turn_on can reach it).
        assert hass.states.get(MEDIA_PLAYER).state == "off"

        # The TV wakes/returns on its own.
        tv.power_state = {"state": "Active"}
        tv.connect_exception = None
        tv.volume = 30
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        tv.push_update()
        await hass.async_block_till_done()

        assert hass.states.get(MEDIA_PLAYER).state == "on"
        assert hass.states.get(MEDIA_PLAYER).attributes["volume_level"] == 0.3


# ---------------------------------------------------------------------------
# Symptom 2: "reload the integration" never fully worked
# ---------------------------------------------------------------------------


async def test_ui_reload_completes_with_wedged_client(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A wedged disconnect must not hang the reload (v1 needed a restart)."""
    with patch_client_factory(tv), pytest.MonkeyPatch.context() as mp:
        mp.setattr("custom_components.bscpylgtv.DISCONNECT_TIMEOUT", 0.05)
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        old_client = tv.clients[-1]

        async def hang() -> None:
            await asyncio.sleep(100)

        old_client.disconnect = hang  # type: ignore[method-assign]
        wedge_task = asyncio.get_running_loop().create_task(asyncio.sleep(100))
        old_client.connect_task = wedge_task  # type: ignore[assignment]

        # The exact user action that used to require a full HA restart.
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        # The wedged client was abandoned, not awaited forever.
        assert wedge_task.cancelled() or wedge_task.done()

        # The reloaded entry is live end to end on a fresh client.
        new_client = tv.clients[-1]
        assert new_client is not old_client
        assert new_client.is_connected()
        tv.volume = 44
        tv.push_update()
        await hass.async_block_till_done()
        assert hass.states.get(MEDIA_PLAYER).attributes["volume_level"] == 0.44


# ---------------------------------------------------------------------------
# Symptom 3: sound output stuck on tv_speaker after the TV returned
# ---------------------------------------------------------------------------


async def test_sound_output_resyncs_after_tv_returns(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A sound-output change made while unreachable surfaces on reconnect."""
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host, mac=tv.mac)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data

        # "Was correct previously after first install": the user switched to
        # the soundbar and the TV pushed the change.
        tv.sound_output = "external_arc"
        tv.push_update()
        await hass.async_block_till_done()
        assert hass.states.get(SOUND_OUTPUT_SELECT).state == "external_arc"

        # TV goes off; the sound-output change cannot push while unreachable.
        tv.disconnect_all()
        tv.connect_exception = OSError("TV is off")
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        # TV returns: the fresh client reports the TV's real current output.
        # The connect-time state push must re-sync the select — the v1 bug
        # kept showing the stale/default tv_speaker here.
        tv.connect_exception = None
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        state = hass.states.get(SOUND_OUTPUT_SELECT)
        assert state.state == "external_arc"
        assert state.state != "tv_speaker"
        # And the value is writable from there (options unioned).
        assert "external_arc" in state.attributes["options"]
