"""webOS 26 (firmware 43.x) blacklisted-certificate regression tests.

These TVs reject bscpylgtv's legacy signed registration manifest with
``403 Pairing rejected: blacklisted certificate detected``. The integration
retries once with the merged
unsigned manifest (mirroring aiowebostv's fix for Home Assistant core):
pairing falls back on ``PyLGTVPairException``; runtime connects are
verified with a real request because the library reports success over a
registration the TV actually rejected.

A transport failure (TV off/unreachable) must NOT trigger the retry: an
unreachable TV should still cost a single connect timeout.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bscpylgtv.exceptions import (
    PyLGTVCmdError,
    PyLGTVPairException,
    PyLGTVServiceNotFoundError,
)
from bscpylgtv.manifest import MANIFEST
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from websockets.exceptions import WebSocketException

from custom_components.bscpylgtv.const import (
    CONF_CLIENT_KEY,
    CONF_HOST,
    CONF_MAC,
    CONF_UNSIGNED_MANIFEST,
    DEFAULT_STATES,
    DOMAIN,
    runtime_states,
)
from custom_components.bscpylgtv.coordinator import build_unsigned_manifest

from .conftest import (
    TVSimulator,
    build_mock_config_entry,
    not_registered_error,
    patch_client_factory,
)

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


def test_runtime_state_policy() -> None:
    """Only unsigned-manifest clients omit software_info."""
    signed_states = runtime_states(unsigned_manifest=False)
    unsigned_states = runtime_states(unsigned_manifest=True)

    assert signed_states == DEFAULT_STATES
    assert signed_states is not DEFAULT_STATES
    assert "software_info" in signed_states
    assert "software_info" not in unsigned_states
    assert set(unsigned_states) == set(DEFAULT_STATES) - {"software_info"}
    assert "system_info" in unsigned_states


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
    assert tv.clients[0].init_kwargs["states"] == DEFAULT_STATES
    assert tv.clients[1].init_kwargs["states"] == runtime_states(unsigned_manifest=True)
    assert tv.clients[0]._rejected_registration  # noqa: SLF001 - test probe
    assert coordinator.client.software_info is None
    assert entry.data[CONF_UNSIGNED_MANIFEST] is True
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
    assert client.init_kwargs["states"] == DEFAULT_STATES
    assert client.software_info == tv.software_info
    assert CONF_UNSIGNED_MANIFEST not in entry.data


async def test_setup_falls_back_on_software_info_permission_error(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """The known static-state permission error selects unsigned mode."""
    tv.software_info = None
    tv.software_info_rejected = True
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert len(tv.clients) == 2
    assert tv.clients[0].init_kwargs["states"] == DEFAULT_STATES
    assert tv.clients[1].init_kwargs["states"] == runtime_states(unsigned_manifest=True)
    assert entry.runtime_data.client.software_info is None
    assert entry.runtime_data.client.is_connected()
    assert entry.data[CONF_UNSIGNED_MANIFEST] is True
    assert entry.runtime_data.last_update_success
    assert hass.states.get(MEDIA_PLAYER).state == "on"


async def test_setup_falls_back_on_registration_error_during_verification(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A rejected registration reported by the probe selects unsigned mode."""

    def create_client(host: str, **kwargs: object) -> object:
        client = tv.create_client(host, **kwargs)
        if len(tv.clients) == 1:
            client.get_power_state = AsyncMock(side_effect=not_registered_error())
        return client

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "custom_components.bscpylgtv.coordinator.WebOsClient",
            create_client,
        )
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert len(tv.clients) == 2
    assert entry.data[CONF_UNSIGNED_MANIFEST] is True
    assert tv.clients[0].init_kwargs["states"] == DEFAULT_STATES
    assert tv.clients[1].init_kwargs["states"] == runtime_states(unsigned_manifest=True)
    assert "software_info" not in tv.clients[1].init_kwargs["states"]
    assert entry.runtime_data.client.is_connected()


@pytest.mark.parametrize(
    "verification_error",
    [
        pytest.param(OSError("network down"), id="oserror"),
        pytest.param(TimeoutError("probe timed out"), id="timeout"),
        pytest.param(WebSocketException("socket closed"), id="websocket"),
        pytest.param(
            PyLGTVServiceNotFoundError("404 no such service or method"),
            id="service-not-found",
        ),
        pytest.param(
            PyLGTVCmdError({"type": "error", "error": "unsupported command"}),
            id="unrelated-command",
        ),
        pytest.param(
            PyLGTVCmdError({"type": "error", "error": "401 insufficient permissions"}),
            id="generic-permission",
        ),
        pytest.param(RuntimeError("unexpected probe error"), id="runtime-error"),
    ],
)
async def test_verification_error_does_not_select_unsigned_mode(
    tv: TVSimulator, verification_error: Exception
) -> None:
    """Only the exact registration rejection permits a compatibility retry."""
    from custom_components.bscpylgtv.coordinator import (
        async_connect_with_manifest_fallback,
    )

    signed_client = tv.create_client(states=DEFAULT_STATES)
    signed_client.get_power_state = AsyncMock(side_effect=verification_error)
    make_unsigned = AsyncMock(side_effect=lambda: tv.create_client())

    with pytest.raises(type(verification_error)):
        await async_connect_with_manifest_fallback(
            signed_client,
            make_unsigned=make_unsigned,
            connect_timeout=1,
        )

    assert len(tv.clients) == 1
    make_unsigned.assert_not_awaited()


async def test_unsigned_verification_registration_error_is_auth_error(
    tv: TVSimulator,
) -> None:
    """A selected unsigned client cannot fall back after losing its key."""
    from custom_components.bscpylgtv.coordinator import (
        async_connect_with_manifest_fallback,
    )

    client = tv.create_client(states=runtime_states(unsigned_manifest=True))
    client.manifest = build_unsigned_manifest()
    client.get_power_state = AsyncMock(side_effect=not_registered_error())
    make_unsigned = AsyncMock()

    with pytest.raises(PyLGTVPairException) as err:
        await async_connect_with_manifest_fallback(
            client,
            make_unsigned=make_unsigned,
            connect_timeout=1,
            unsigned_preferred=True,
        )

    assert isinstance(err.value.__cause__, PyLGTVCmdError)
    make_unsigned.assert_not_awaited()


async def test_verification_transport_error_does_not_persist_unsigned_mode(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A transient probe failure leaves an old entry in signed mode."""

    def create_client(host: str, **kwargs: object) -> object:
        client = tv.create_client(host, **kwargs)
        client.get_power_state = AsyncMock(side_effect=OSError("network down"))
        return client

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "custom_components.bscpylgtv.coordinator.WebOsClient",
            create_client,
        )
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert len(tv.clients) == 1
    assert CONF_UNSIGNED_MANIFEST not in entry.data
    assert entry.state is ConfigEntryState.LOADED


async def test_unrelated_command_error_does_not_select_unsigned_mode(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """Unrelated command failures do not trigger compatibility fallback."""
    tv.connect_exception = PyLGTVCmdError({"error": "unsupported command"})
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert len(tv.clients) == 1
    assert entry.data.get(CONF_UNSIGNED_MANIFEST) is not True


async def test_setup_uses_persisted_unsigned_manifest_directly(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """An unsigned pairing mode starts runtime unsigned without a signed probe."""
    tv.manifest_rejected = True
    with patch_client_factory(tv):
        entry = build_mock_config_entry(
            hass,
            host=tv.host,
            data={
                CONF_HOST: tv.host,
                CONF_CLIENT_KEY: "stored-key",
                CONF_UNSIGNED_MANIFEST: True,
            },
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_UNSIGNED_MANIFEST] is True
    assert len(tv.clients) == 1
    assert "signed" not in entry.runtime_data.client.manifest
    assert entry.runtime_data.client.is_connected()
    assert entry.runtime_data.client.init_kwargs["states"] == runtime_states(
        unsigned_manifest=True
    )
    assert "software_info" not in entry.runtime_data.client.init_kwargs["states"]


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

    # The successful initial fallback was persisted, so reconnect is unsigned.
    assert len(tv.clients) == before + 1
    assert "signed" not in coordinator.client.manifest
    assert coordinator.client.is_connected()
    assert entry.data[CONF_UNSIGNED_MANIFEST] is True
    assert coordinator.client.init_kwargs["states"] == runtime_states(
        unsigned_manifest=True
    )


async def test_watchdog_reconnect_uses_persisted_unsigned_manifest_directly(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A known unsigned TV reconnects with one unsigned candidate."""
    tv.manifest_rejected = True
    with patch_client_factory(tv):
        entry = build_mock_config_entry(
            hass,
            host=tv.host,
            mac=tv.mac,
            data={
                CONF_HOST: tv.host,
                CONF_CLIENT_KEY: "stored-key",
                CONF_UNSIGNED_MANIFEST: True,
                "mac": tv.mac,
            },
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data
        assert len(tv.clients) == 1

        tv.disconnect_all()
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert len(tv.clients) == 2
    assert "signed" not in coordinator.client.manifest
    assert coordinator.client.is_connected()
    assert all(
        client.init_kwargs["states"] == runtime_states(unsigned_manifest=True)
        for client in tv.clients
    )


async def test_recovery_reconnect_keeps_compatibility_states(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """Command recovery reuses persisted unsigned states."""
    with patch_client_factory(tv):
        entry = build_mock_config_entry(
            hass,
            host=tv.host,
            data={
                CONF_HOST: tv.host,
                CONF_CLIENT_KEY: "stored-key",
                CONF_UNSIGNED_MANIFEST: True,
            },
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data

        tv.disconnect_all()
        await coordinator.async_recover()

    assert len(tv.clients) == 2
    assert coordinator.client is tv.clients[-1]
    assert "signed" not in coordinator.client.manifest
    assert coordinator.client.init_kwargs["states"] == runtime_states(
        unsigned_manifest=True
    )


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
    assert entry.data.get(CONF_UNSIGNED_MANIFEST) is not True


async def test_runtime_fallback_does_not_invent_mac(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """Unsigned clients do not request software_info for MAC self-heal."""
    tv.manifest_rejected = True
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    coordinator = entry.runtime_data
    assert coordinator.client.client_key == "stored-key"
    assert coordinator.client.software_info is None
    assert CONF_MAC not in entry.data
    assert coordinator.turn_on_available is False


async def test_unsigned_runtime_preserves_manual_mac_for_wol(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A stored MAC remains the Wake-on-LAN path without software_info."""
    manual_mac = "11:22:33:44:55:66"
    with patch_client_factory(tv):
        entry = build_mock_config_entry(
            hass,
            host=tv.host,
            data={
                CONF_HOST: tv.host,
                CONF_CLIENT_KEY: "stored-key",
                CONF_MAC: manual_mac,
                CONF_UNSIGNED_MANIFEST: True,
            },
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.runtime_data.client.software_info is None
    assert entry.data[CONF_MAC] == manual_mac
    assert entry.runtime_data.turn_on_available is True
    sent: list[tuple[bytes, tuple[str, int]]] = []
    sock = MagicMock()
    sock.__enter__.return_value = sock
    sock.sendto = lambda data, addr: sent.append((bytes(data), addr))
    with patch(
        "custom_components.bscpylgtv.media_player.socket.socket", return_value=sock
    ):
        await hass.services.async_call(
            "media_player", "turn_on", {"entity_id": MEDIA_PLAYER}, blocking=True
        )
    mac_bytes = bytes.fromhex(manual_mac.replace(":", ""))
    assert sent == [(b"\xff" * 6 + mac_bytes * 16, ("<broadcast>", 9))]


async def test_setup_unregistered_key_after_unsigned_retry_starts_reauth(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """Both manifests rejecting the key means credentials are invalid."""
    tv.client_key_rejected = True
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host)
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]
    assert len(tv.clients) == 2
    assert "signed" in tv.clients[0].manifest
    assert "signed" not in tv.clients[1].manifest
    assert CONF_UNSIGNED_MANIFEST not in entry.data


async def test_persisted_unsigned_unregistered_key_starts_reauth(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A known unsigned TV reports a lost registration as auth failure."""
    tv.client_key_rejected = True
    with patch_client_factory(tv):
        entry = build_mock_config_entry(
            hass,
            host=tv.host,
            data={
                CONF_HOST: tv.host,
                CONF_CLIENT_KEY: "stored-key",
                CONF_UNSIGNED_MANIFEST: True,
            },
        )
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]
    assert len(tv.clients) == 1
    assert "signed" not in tv.clients[0].manifest
    assert entry.data[CONF_UNSIGNED_MANIFEST] is True


async def test_persisted_unsigned_reconnect_unregistered_key_starts_reauth(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A lost registration during watchdog reconnect starts reauth."""
    with patch_client_factory(tv):
        entry = build_mock_config_entry(
            hass,
            host=tv.host,
            data={
                CONF_HOST: tv.host,
                CONF_CLIENT_KEY: "stored-key",
                CONF_UNSIGNED_MANIFEST: True,
            },
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data

        tv.disconnect_all()
        tv.client_key_rejected = True
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]
    assert len(tv.clients) == 2
    assert all("signed" not in client.manifest for client in tv.clients)
    assert entry.data[CONF_UNSIGNED_MANIFEST] is True


@pytest.mark.parametrize(
    "connect_error",
    [
        pytest.param(OSError("network down"), id="oserror"),
        pytest.param(TimeoutError("connect timed out"), id="timeout"),
        pytest.param(WebSocketException("socket closed"), id="websocket"),
        pytest.param(
            PyLGTVServiceNotFoundError("404 no such service or method"),
            id="service-not-found",
        ),
        pytest.param(
            PyLGTVCmdError({"type": "error", "error": "unsupported command"}),
            id="unrelated-command",
        ),
    ],
)
async def test_persisted_unsigned_connection_error_does_not_start_reauth(
    hass: HomeAssistant, tv: TVSimulator, connect_error: Exception
) -> None:
    """Ordinary unsigned connection failures keep normal retry semantics."""
    tv.connect_exception = connect_error
    with patch_client_factory(tv):
        entry = build_mock_config_entry(
            hass,
            host=tv.host,
            data={
                CONF_HOST: tv.host,
                CONF_CLIENT_KEY: "stored-key",
                CONF_UNSIGNED_MANIFEST: True,
            },
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(tv.clients) == 1
    assert entry.data[CONF_UNSIGNED_MANIFEST] is True


async def test_persisted_unsigned_reconnect_oserror_does_not_start_reauth(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A transient watchdog outage stays a connection failure."""
    with patch_client_factory(tv):
        entry = build_mock_config_entry(
            hass,
            host=tv.host,
            data={
                CONF_HOST: tv.host,
                CONF_CLIENT_KEY: "stored-key",
                CONF_MAC: tv.mac,
                CONF_UNSIGNED_MANIFEST: True,
            },
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data

        tv.disconnect_all()
        tv.connect_exception = OSError("network down")
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert coordinator.last_update_success
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(tv.clients) == 2
    assert entry.data[CONF_UNSIGNED_MANIFEST] is True
