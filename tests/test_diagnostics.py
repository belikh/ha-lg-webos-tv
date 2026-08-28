"""Tests for the diagnostics snapshot (plan AD-18, AC-25)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import REDACTED
from homeassistant.core import HomeAssistant

from custom_components.bscpylgtv.const import DOMAIN
from custom_components.bscpylgtv.diagnostics import (
    TO_REDACT,
    async_get_config_entry_diagnostics,
)

from .conftest import TVSimulator, build_mock_config_entry, patch_client_factory

# Every key that must never survive redaction (plan AD-18 superset).
MANDATORY_REDACTED_KEYS = (
    "client_key",
    "host",
    "mac",
    "ip_address",
    "unique_id",
    "device_id",
    "deviceUUID",
    "macAddress",
    "icon",
    "largeIcon",
    "signature",
    "sessionId",
)


def _collect_values(data: Any, key: str, hits: list[Any]) -> None:
    """Walk the whole diagnostics tree collecting values for ``key``."""
    if isinstance(data, dict):
        for k, v in data.items():
            if k == key:
                hits.append(v)
            _collect_values(v, key, hits)
    elif isinstance(data, list):
        for v in data:
            _collect_values(v, key, hits)


def _assert_fully_redacted(data: Any) -> None:
    """Every redacted key present in the tree carries only REDACTED values."""
    for key in MANDATORY_REDACTED_KEYS:
        hits: list[Any] = []
        _collect_values(data, key, hits)
        assert hits, f"{key} missing from diagnostics snapshot"
        assert all(h is REDACTED or h == REDACTED for h in hits), (key, hits)


def _seed_sensitive_payloads(tv: TVSimulator) -> None:
    """Plant every sensitive key the TV payloads can carry.

    The snapshot carries the pushed state dicts only (apps/inputs/channels
    are reduced to counts), so the icon keys ride on power_state.
    """
    tv.power_state = {
        "state": "Active",
        "macAddress": tv.mac,
        "sessionId": "session-1234",
        "signature": "sig-abcdef",
        "icon": "/usr/share/icons/tv.png",
        "largeIcon": "http://192.168.1.42:3000/icon/tv.png",
    }


async def test_diagnostics_redacts_every_sensitive_key(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """Loaded entry: all 12 keys redacted; lists reduced to counts."""
    _seed_sensitive_payloads(tv)
    with patch_client_factory(tv):
        entry = build_mock_config_entry(
            hass,
            host=tv.host,
            mac=tv.mac,
            data={
                "host": tv.host,
                "client_key": "stored-key",
                "mac": tv.mac,
                "ip_address": "192.168.1.42",  # legacy v1 key
            },
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    _assert_fully_redacted(diagnostics)
    # And the set implemented by the module covers the mandatory superset.
    assert set(MANDATORY_REDACTED_KEYS) <= TO_REDACT

    client = diagnostics["client"]
    # Lists appear ONLY as counts.
    for listed, counted in (
        ("apps", "apps_count"),
        ("inputs", "inputs_count"),
        ("channels", "channels_count"),
    ):
        assert listed not in client
        assert counted in client
    assert client["apps_count"] == 3
    assert client["inputs_count"] == 2
    assert client["channels_count"] == len(tv.channels)
    # Non-sensitive live state survives.
    assert client["sound_output"] == "tv_speaker"
    assert client["volume"] == 12
    assert client["system_info"]["modelName"] == "OLED55C2"


async def test_diagnostics_entry_not_loaded_safe_snapshot(
    hass: HomeAssistant,
) -> None:
    """A not-loaded entry (failed setup) yields a None snapshot, counts 0."""
    entry = build_mock_config_entry(hass)
    assert entry.domain == DOMAIN
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    client = diagnostics["client"]
    assert client["is_registered"] is None
    assert client["is_connected"] is None
    assert client["power_state"] is None
    assert client["sound_output"] is None
    assert client["current_app_id"] is None
    assert client["apps_count"] == 0
    assert client["inputs_count"] == 0
    assert client["channels_count"] == 0
    # The entry half is still present (and redacted where needed).
    assert diagnostics["entry"]["entry_id"] == entry.entry_id
