"""Tests for the push coordinator + watchdog (plan §6, AC-1..5, AC-15)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from bscpylgtv.exceptions import PyLGTVCmdError, PyLGTVPairException
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.bscpylgtv.const import SCAN_INTERVAL
from custom_components.bscpylgtv.coordinator import (
    BscpylgtvCoordinator,
    release_client,
    update_client_key,
    update_mac_address,
)

from .conftest import TVSimulator, build_mock_config_entry, patch_client_factory

MEDIA_PLAYER = "media_player.lg_webos_tv_oled55c2"


@asynccontextmanager
async def scenario(
    hass: HomeAssistant, tv: TVSimulator, *, mac: str | None = None
) -> AsyncIterator[BscpylgtvCoordinator]:
    """Set up one entry with the client factory patched for the scenario."""
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host, mac=mac)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry.runtime_data


def _hanging_coro() -> Any:
    """An AsyncMock whose coroutine hangs forever."""

    async def hang(*_a: Any, **_k: Any) -> None:
        await asyncio.sleep(100)

    return AsyncMock(side_effect=hang)


async def test_coordinator_shape(integration: Any) -> None:
    """AC-1: DataUpdateCoordinator[None], 10 s supervisory interval."""
    coordinator = integration.coordinator
    assert isinstance(coordinator, BscpylgtvCoordinator)
    assert coordinator.update_interval == SCAN_INTERVAL == timedelta(seconds=10)


async def test_push_callback_updates_entities(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A TV push flows through the coordinator into entity state."""
    async with scenario(hass, tv):
        tv.volume = 40
        tv.muted = True
        tv.push_update()
        await hass.async_block_till_done()
        state = hass.states.get(MEDIA_PLAYER)
        assert state.attributes["volume_level"] == 0.4
        assert state.attributes["is_volume_muted"] is True


async def test_callback_exception_does_not_propagate(
    hass: HomeAssistant, tv: TVSimulator, caplog: Any
) -> None:
    """PR#8 regression: a callback exception must not kill the task."""
    async with scenario(hass, tv) as coordinator:
        boom = RuntimeError("callback boom")

        def broken(_client: Any) -> None:
            raise boom

        coordinator.async_set_updated_data = broken  # type: ignore[method-assign]
        with caplog.at_level(logging.ERROR):
            # Must not raise: the library's callback_handler would
            # otherwise permanently kill the subscription task.
            await coordinator.async_handle_update(tv.clients[0])
        assert any(r.exc_info and r.exc_info[1] is boom for r in caplog.records)


async def test_callback_ignored_when_last_update_failed(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """Teardown-noise callbacks don't flip entities back to available."""
    async with scenario(hass, tv) as coordinator:
        coordinator.last_update_success = False
        calls: list[None] = []
        original = coordinator.async_set_updated_data

        def spy(data: None) -> None:
            calls.append(data)
            original(data)

        coordinator.async_set_updated_data = spy  # type: ignore[method-assign]
        await coordinator.async_handle_update(tv.clients[0])
        assert calls == []


async def test_watchdog_reconnects_after_drop(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """AC-3: a dropped socket reconnects without an HA restart."""
    async with scenario(hass, tv, mac=tv.mac) as coordinator:
        old_client = tv.clients[0]
        tv.disconnect_all()  # socket died

        await coordinator.async_refresh()
        await hass.async_block_till_done()

        new_client = coordinator.client
        assert new_client is not old_client
        assert new_client.is_connected()
        # Callback re-registered on the FRESH client before it connected.
        assert coordinator.state_update_task in new_client.state_update_callbacks
        # And the new push path works end to end.
        tv.volume = 55
        tv.push_update()
        await hass.async_block_till_done()
        assert hass.states.get(MEDIA_PLAYER).attributes["volume_level"] == 0.55
        assert coordinator.config_entry.state is ConfigEntryState.LOADED


async def test_zombie_probe_and_swap(hass: HomeAssistant, tv: TVSimulator) -> None:
    """AC-4: an unresponsive-but-'connected' client is abandoned."""
    async with scenario(hass, tv) as coordinator:
        zombie = tv.clients[0]
        # Give the zombie a live connect task so the abandon path has teeth.
        zombie_task = asyncio.get_running_loop().create_task(asyncio.sleep(100))
        zombie.connect_task = zombie_task  # type: ignore[assignment]
        # is_connected() stays True but the probe times out (dead socket).
        zombie.get_power_state = _hanging_coro()  # type: ignore[method-assign]

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("custom_components.bscpylgtv.coordinator.PROBE_TIMEOUT", 0.05)
            await coordinator.async_refresh()
        await hass.async_block_till_done()

        assert coordinator.client is not zombie
        assert coordinator.client.is_connected()
        # Zombie abandoned: never awaited disconnect, task cancelled.
        assert zombie_task.cancelled() or zombie_task.done()


async def test_probe_error_treated_as_dead(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A probe that raises (instead of hanging) also triggers a swap."""
    async with scenario(hass, tv) as coordinator:
        zombie = tv.clients[0]
        zombie.get_power_state = AsyncMock(side_effect=TimeoutError("probe timeout"))  # type: ignore[method-assign]

        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert coordinator.client is not zombie
        assert coordinator.client.is_connected()


async def test_reconnect_pair_error_raises_auth_failed(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """AC-5: pairing failure during reconnect surfaces as auth failure."""
    async with scenario(hass, tv) as coordinator:
        tv.disconnect_all()
        tv.connect_exception = PyLGTVPairException("key revoked")
        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()


async def test_reconnect_unavailable_without_mac(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """AC-5: no MAC + failing reconnect → UpdateFailed (unavailable)."""
    # Keep the MAC self-heal out of the picture: software_info carries a
    # non-MAC device_id so the entry truly has no wake path.
    tv.software_info = {**tv.software_info, "device_id": "webos-device"}
    async with scenario(hass, tv, mac=None) as coordinator:
        assert coordinator.turn_on_available is False
        tv.disconnect_all()
        tv.connect_exception = OSError("no route to host")
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


async def test_reconnect_quiet_with_mac(hass: HomeAssistant, tv: TVSimulator) -> None:
    """AC-5: with a MAC the entry stays quiet (available showing OFF)."""
    async with scenario(hass, tv, mac=tv.mac) as coordinator:
        assert coordinator.turn_on_available is True
        tv.disconnect_all()
        tv.connect_exception = OSError("no route to host")
        assert await coordinator._async_update_data() is None


async def test_reconnect_recovers_when_tv_returns(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A transient TV-off window: first refresh quiet, second reconnects."""
    async with scenario(hass, tv, mac=tv.mac) as coordinator:
        tv.disconnect_all()
        tv.connect_exception = OSError("warming up")
        assert await coordinator._async_update_data() is None
        tv.connect_exception = None
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert coordinator.client.is_connected()


async def test_update_client_key_rotation(hass: HomeAssistant, tv: TVSimulator) -> None:
    """A rotated key is persisted; entry.data is never mutated in place."""
    async with scenario(hass, tv) as coordinator:
        entry = coordinator.config_entry
        original_data = dict(entry.data)
        coordinator.client.client_key = "rotated-key"
        update_client_key(hass, entry, coordinator.client)
        assert entry.data["client_key"] == "rotated-key"
        assert original_data["client_key"] == "stored-key"
        # No-op when unchanged.
        update_client_key(hass, entry, coordinator.client)
        assert entry.data["client_key"] == "rotated-key"


async def test_update_client_key_ignores_empty(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """An empty client_key never clobbers the stored key."""
    async with scenario(hass, tv) as coordinator:
        entry = coordinator.config_entry
        coordinator.client.client_key = None
        update_client_key(hass, entry, coordinator.client)
        assert entry.data["client_key"] == "stored-key"


async def test_update_mac_address_self_heal(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """The MAC is adopted from software_info when missing or changed."""
    async with scenario(hass, tv, mac=None) as coordinator:
        entry = coordinator.config_entry
        update_mac_address(hass, entry, coordinator.client)
        assert entry.data["mac"] == tv.mac
        # A different (valid) MAC overwrites.
        tv.software_info = {**tv.software_info, "device_id": "11:22:33:44:55:66"}
        update_mac_address(hass, entry, coordinator.client)
        assert entry.data["mac"] == "11:22:33:44:55:66"
        # Non-MAC device_id values are ignored.
        tv.software_info = {**tv.software_info, "device_id": "not-a-mac"}
        update_mac_address(hass, entry, coordinator.client)
        assert entry.data["mac"] == "11:22:33:44:55:66"


async def test_watchdog_updates_key_and_mac_after_reconnect(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """Successful reconnects persist rotated keys/MACs (AD-2)."""
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host, mac=None)
        original_create = tv.create_client

        def create_with_rotation(host: str | None = None, **kwargs: Any) -> Any:
            client = original_create(host, **kwargs)
            client.client_key = "rotated-key"
            return client

        tv.create_client = create_with_rotation  # type: ignore[method-assign]
        tv.software_info = {**tv.software_info, "device_id": "11:22:33:44:55:66"}
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data

        tv.disconnect_all()
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert entry.data["client_key"] == "rotated-key"
    assert entry.data["mac"] == "11:22:33:44:55:66"


async def test_async_recover_reconnects_for_retry(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """The cmd-decorator recovery pass reconnects a dead client."""
    async with scenario(hass, tv) as coordinator:
        tv.disconnect_all()
        await coordinator.async_recover()
        assert coordinator.client.is_connected()
        assert coordinator.client is not tv.clients[0]


async def test_async_recover_swallows_connection_errors(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """Recovery stays quiet so the retry can fail with a real error."""
    async with scenario(hass, tv) as coordinator:
        tv.disconnect_all()
        tv.connect_exception = OSError("still down")
        await coordinator.async_recover()  # must not raise
        tv.connect_exception = PyLGTVCmdError("cmd dead")
        await coordinator.async_recover()  # must not raise either


def test_release_client_cancels_task(tv: TVSimulator) -> None:
    """release_client cancels a live connect task, ignores None."""
    assert release_client(None) is None
    loop = asyncio.new_event_loop()
    try:
        task = loop.create_task(asyncio.sleep(100))
        client = tv.create_client()
        client.connect_task = task  # type: ignore[assignment]
        release_client(client)
        loop.run_until_complete(asyncio.sleep(0))
        assert task.cancelled()
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Library teardown-compat (raw coroutines vs asyncio.wait, Python 3.11+)
# ---------------------------------------------------------------------------


async def test_state_update_callback_returns_task(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """The registered callback returns a Task, never a coroutine.

    bscpylgtv's connect_handler teardown collects ``callback(self)``
    results into a set and passes it to ``asyncio.wait`` — raw
    coroutines make wait() raise TypeError on Python 3.11+, killing
    disconnect()/unload (observed on real hardware; found while
    validating the issue-#9 fixes). A Task works at every call site.
    """
    async with scenario(hass, tv) as coordinator:
        result = coordinator.state_update_task(tv.clients[0])
        assert isinstance(result, asyncio.Task)
        # Completes exception-free (async_handle_update is shielded).
        await asyncio.wait_for(result, timeout=5)


async def test_teardown_closeout_is_wait_safe(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """The library's closeout pattern (wait over callback results) survives."""
    async with scenario(hass, tv) as coordinator:
        client = tv.clients[0]
        closeout = {coordinator.state_update_task(client)}
        done, pending = await asyncio.wait(closeout, timeout=5)
        assert pending == set()
        assert done == closeout

        # Contrast: what the library would do with a plain async
        # callback — exactly the crash observed on real hardware
        # (asyncio.wait rejects raw coroutines on Python 3.11+).
        async def raw(_client: Any) -> None:
            pass

        with pytest.raises(TypeError):
            await asyncio.wait({raw(client)}, timeout=5)
