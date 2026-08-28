"""Tests for integration setup/unload/migration (plan §6, AC-12/14/21/28)."""

from __future__ import annotations

import gc
import logging
import warnings
from pathlib import Path
from typing import Any

import pytest
from bscpylgtv.exceptions import PyLGTVPairException
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bscpylgtv.const import DOMAIN

from .conftest import TVSimulator, build_mock_config_entry, patch_client_factory

LOGGER_NAME = "custom_components.bscpylgtv"


async def test_setup_unload_reload(hass: HomeAssistant, tv: TVSimulator) -> None:
    """Entry sets up, unloads, and sets up again (AC-28)."""
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        assert entry.runtime_data.client is tv.clients[0]

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED
        assert not tv.clients[0].is_connected()

        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED


async def test_services_registered_on_setup(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """async_setup registers the six domain services (AC-24)."""
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
    for service in (
        "button",
        "command",
        "select_sound_output",
        "launch_app",
        "take_screenshot",
        "set_settings",
    ):
        assert hass.services.has_service(DOMAIN, service), service


async def test_keyless_entry_fails_to_reauth(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A keyless entry cannot pair in the background: reauth (plan §7)."""
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host, client_key=None)
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == "reauth"
    # No client was ever built for a keyless entry.
    assert tv.clients == []


async def test_setup_tv_off_stays_loaded_without_warning(
    hass: HomeAssistant, tv: TVSimulator, caplog: Any
) -> None:
    """An unreachable TV at setup must not fail the entry or warn (AC-14)."""
    tv.connect_exception = OSError("TV is off")
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    warnings = [
        r
        for r in caplog.records
        if r.levelno >= logging.WARNING and r.name.startswith(LOGGER_NAME)
    ]
    assert not warnings


async def test_setup_pairing_failure_raises_auth_failed(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A rejected key during setup starts the reauth flow (AC-5)."""
    tv.connect_exception = PyLGTVPairException("TV rejected the key")
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host)
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN)


async def test_callback_registered_before_connect(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """The push callback is registered on the client (AD-2 order)."""
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.runtime_data.state_update_task in tv.clients[0].state_update_callbacks


async def test_no_first_refresh_push_coordinator(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """Setup never forces a first refresh (AC-15): the TV stays off-friendly."""
    tv.connect_exception = OSError("off")
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    coordinator = entry.runtime_data
    # last_update_success is untouched: no refresh ran, none was needed.
    assert coordinator.last_update_success is True


async def test_hass_stop_tears_down_client(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """EVENT_HOMEASSISTANT_STOP disconnects the client (bounded)."""
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    assert not tv.clients[0].is_connected()


async def test_unload_abandons_wedged_client(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A hanging disconnect never blocks unload; the zombie is abandoned."""
    import asyncio

    with patch_client_factory(tv), pytest.MonkeyPatch.context() as mp:
        mp.setattr("custom_components.bscpylgtv.DISCONNECT_TIMEOUT", 0.05)
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        client = tv.clients[0]

        async def hang() -> None:
            await asyncio.sleep(100)

        client.disconnect = hang  # type: ignore[method-assign]
        zombie_task = asyncio.get_running_loop().create_task(asyncio.sleep(100))
        client.connect_task = zombie_task  # type: ignore[assignment]

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
    # The wedged client was abandoned: its connect task got cancelled.
    assert zombie_task.cancelled() or zombie_task.done()


# ---------------------------------------------------------------------------
# Migration (plan §7, AC-21)
# ---------------------------------------------------------------------------


def _write_legacy_key_db(config_dir: str, filename: str, host: str, key: str) -> str:
    """Create a v1 sqlitedict key file exactly like bscpylgtv 0.5.3 did."""
    from sqlitedict import SqliteDict

    path = Path(config_dir) / filename
    with SqliteDict(str(path)) as db:
        db[host] = key
        db.commit()
    return str(path)


async def test_migrate_v1_entry_with_key_file(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """v1 (ip_address + key_file) migrates to v2 {host, client_key}."""
    config_dir = hass.config.config_dir
    _write_legacy_key_db(
        config_dir, "bscpylgtv_192.168.1.42.sqlite", tv.host, "legacy-key"
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=0,
        unique_id=tv.host,
        data={
            "ip_address": tv.host,
            "key_file": "bscpylgtv_192.168.1.42.sqlite",
            "name": "Living Room TV",
        },
        title="Living Room TV",
    )
    entry.add_to_hass(hass)
    with patch_client_factory(tv):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.version == 2
    assert entry.minor_version == 1
    # The MAC was self-healed from software_info after the live connect.
    assert entry.data == {
        "host": tv.host,
        "client_key": "legacy-key",
        "mac": tv.mac,
    }
    # The sqlite file is deliberately not deleted.
    assert (Path(config_dir) / "bscpylgtv_192.168.1.42.sqlite").is_file()


@pytest.mark.filterwarnings(
    # sqlitedict's background writer thread dies on the corrupt fixture
    # file after the test body moved on; the fallback itself is asserted.
    "ignore::pytest.PytestUnhandledThreadExceptionWarning"
)
async def test_migrate_v1_corrupt_key_file_falls_back_to_reauth(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """An unreadable key file degrades to a keyless entry → reauth (§7)."""
    config_dir = hass.config.config_dir
    (Path(config_dir) / "corrupt.sqlite").write_bytes(b"this is not sqlite")
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=0,
        unique_id=tv.host,
        data={"ip_address": tv.host, "key_file": "corrupt.sqlite"},
        title="Living Room TV",
    )
    entry.add_to_hass(hass)
    with patch_client_factory(tv):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    # Migration itself succeeded (v2, host only) — silently keyless.
    assert entry.version == 2
    assert entry.data == {"host": tv.host}
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    # sqlitedict's thread died on the corrupt file and left its connection
    # to the GC; finalize it here (filter scoped to exactly this cleanup)
    # so the ResourceWarning cannot leak into a later test's summary.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        gc.collect()


async def test_migrate_v1_missing_key_file_falls_back_to_reauth(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A missing key file degrades to a keyless entry → reauth."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=0,
        unique_id=tv.host,
        data={"ip_address": tv.host, "key_file": "does-not-exist.sqlite"},
        title="Living Room TV",
    )
    entry.add_to_hass(hass)
    with patch_client_factory(tv):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.version == 2
    assert entry.data == {"host": tv.host}


async def test_migrate_v1_no_host_fails(hass: HomeAssistant) -> None:
    """A v1 entry without ip_address cannot migrate."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=0,
        unique_id="whatever",
        data={"name": "TV"},
        title="Living Room TV",
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.MIGRATION_ERROR


async def test_migrate_v1_carries_mac(hass: HomeAssistant, tv: TVSimulator) -> None:
    """A v1 MAC carries over into the v2 data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=0,
        unique_id=tv.host,
        data={"ip_address": tv.host, "mac": "11:22:33:44:55:66"},
        title="Living Room TV",
    )
    entry.add_to_hass(hass)
    with patch_client_factory(tv):
        # Keyless after migration (no key_file): reauth is expected.
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.data == {"host": tv.host, "mac": "11:22:33:44:55:66"}


async def test_migrate_v2_minor_version(hass: HomeAssistant, tv: TVSimulator) -> None:
    """A v2 entry below the current minor version is bumped."""
    entry = build_mock_config_entry(hass, host=tv.host, minor_version=0)
    with patch_client_factory(tv):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.version == 2
    assert entry.minor_version == 1


# ---------------------------------------------------------------------------
# Lazy unique_id fix (plan §7, AC-12)
# ---------------------------------------------------------------------------


async def test_lazy_unique_id_ip_to_uuid(hass: HomeAssistant, tv: TVSimulator) -> None:
    """A live hello fixes a legacy IP unique_id before platform setup."""
    from homeassistant.helpers import entity_registry as er

    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host, unique_id=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.unique_id == tv.device_uuid
    # Entities were created against the new UUID from the start.
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("media_player", DOMAIN, tv.device_uuid)
    assert not [
        e for e in registry.entities.values() if e.unique_id and tv.host in e.unique_id
    ]


async def test_lazy_unique_id_duplicate_guard(
    hass: HomeAssistant, tv: TVSimulator, caplog: Any
) -> None:
    """When another entry already owns the UUID, keep the old id (R-11)."""
    with patch_client_factory(tv):
        other = build_mock_config_entry(
            hass,
            host="192.168.1.99",
            unique_id=tv.device_uuid,
            title="Same TV elsewhere",
        )
        entry = build_mock_config_entry(hass, host=tv.host, unique_id=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.unique_id == tv.host  # unchanged
    assert other.unique_id == tv.device_uuid
    assert any(
        r.name == LOGGER_NAME
        and r.levelno == logging.WARNING
        and "unique_id" in r.message
        for r in caplog.records
    )


async def test_uuid_unique_id_untouched(hass: HomeAssistant, tv: TVSimulator) -> None:
    """A healthy v2 unique_id is never rewritten."""
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host, unique_id=tv.device_uuid)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.unique_id == tv.device_uuid
