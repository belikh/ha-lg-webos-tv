"""webOS 26 (firmware 43.x) blacklisted-certificate regression tests.

These TVs reject bscpylgtv's legacy signed registration manifest with
``403 Pairing rejected: blacklisted certificate detected`` and invalidate
existing pairing keys. The integration retries once with the merged
unsigned manifest (mirroring aiowebostv's fix for Home Assistant core):
pairing falls back on ``PyLGTVPairException``; runtime connects are
verified with a real request because the library reports success over a
registration the TV actually rejected.

A transport failure (TV off/unreachable) must NOT trigger the retry: an
unreachable TV should still cost a single connect timeout.
"""

from __future__ import annotations

from bscpylgtv.manifest import MANIFEST
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.bscpylgtv.coordinator import build_unsigned_manifest

from .conftest import TVSimulator, build_mock_config_entry, patch_client_factory

MEDIA_PLAYER = "media_player.lg_webos_tv_oled55c2"


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------


def test_build_unsigned_manifest_merges_signed_permissions() -> None:
    """Signatures are dropped; signed-only permissions move to the outer block."""
    manifest = build_unsigned_manifest()
    assert "signed" not in manifest
    assert "signatures" not in manifest
    permissions = manifest["permissions"]
    assert len(permissions) == len(set(permissions))
    for permission in (
        # Outer set (unchanged)
        "CONTROL_POWER",
        "READ_POWER_STATE",
        "READ_STORAGE_DEVICE_LIST",
        # Signed-only set, merged in (WHAT the pairing prompt grants)
        "WRITE_SETTINGS",
        "READ_UPDATE_INFO",
        "READ_LGE_SDX",
    ):
        assert permission in permissions, permission
    # The library's constant is never mutated.
    assert "signed" in MANIFEST
    assert "signatures" in MANIFEST


# ---------------------------------------------------------------------------
# Runtime connect fallback
# ---------------------------------------------------------------------------


async def test_setup_falls_back_to_unsigned_manifest(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A stored-key connect rejected by the TV retries unsigned and works."""
    tv.manifest_rejected = True
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    coordinator = entry.runtime_data
    assert "signed" not in coordinator.client.manifest
    assert coordinator.client.is_connected()
    # The signed candidate was silently rejected, the unsigned one works.
    assert len(tv.clients) == 2
    assert tv.clients[0]._rejected_registration  # noqa: SLF001 - test probe
    # End to end: entities are live again on this TV.
    assert hass.states.get(MEDIA_PLAYER).state == "on"


async def test_setup_keeps_signed_manifest_when_accepted(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """TVs that accept the signed manifest keep its elevated permissions."""
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Exactly one connect: no unsigned retry on a healthy TV.
    assert len(tv.clients) == 1
    client = entry.runtime_data.client
    assert "signed" in client.manifest


async def test_watchdog_reconnect_falls_back_to_unsigned(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A dropped connection on webOS 26 reconnects with the unsigned manifest."""
    tv.manifest_rejected = True
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host, mac=tv.mac)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data
        assert "signed" not in coordinator.client.manifest

        before = len(tv.clients)
        tv.disconnect_all()  # socket died / TV restarted
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    # One rejected signed candidate + one working unsigned candidate.
    assert len(tv.clients) == before + 2
    assert "signed" not in coordinator.client.manifest
    assert coordinator.client.is_connected()


async def test_setup_transport_failure_does_not_retry(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """An unreachable TV costs one connect attempt, not two."""
    tv.connect_exception = OSError("unreachable")
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Setup tolerates an off TV; no unsigned retry was attempted.
    assert entry.state is ConfigEntryState.LOADED
    assert len(tv.clients) == 1


async def test_runtime_fallback_keeps_self_heal_hooks(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """The unsigned fallback client behaves like any other runtime client."""
    tv.manifest_rejected = True
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        client = entry.runtime_data.client
        # Key/MAC self-heal hooks run on the fallback client too.
        assert client.client_key == "stored-key"
        assert entry.data.get("mac") == tv.mac
