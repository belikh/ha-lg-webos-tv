"""Tests for the config flow: user/pairing/ssdp/reauth/reconfigure/options."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from bscpylgtv.exceptions import PyLGTVPairException
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE
from homeassistant.const import CONF_HOST, CONF_MAC
from homeassistant.core import HomeAssistant
from homeassistant.helpers.service_info.ssdp import (
    ATTR_UPNP_FRIENDLY_NAME,
    ATTR_UPNP_UDN,
    SsdpServiceInfo,
)

from custom_components.bscpylgtv.const import CONF_CLIENT_KEY, CONF_SOURCES, DOMAIN

from .conftest import TVSimulator, build_mock_config_entry, patch_client_factory

HOST = "192.168.1.42"
UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def ssdp_info(
    host: str = HOST,
    udn: str = f"uuid:{UUID}",
    name: str = "[LG] webOS TV OLED55C2",
) -> SsdpServiceInfo:
    """Build a discovery payload like the webOS SSDP scanner delivers."""
    return SsdpServiceInfo(
        ssdp_location=f"http://{host}:1400/ssdp/device-desc.xml",
        ssdp_st="urn:lge-com:service:webos-second-screen:1",
        ssdp_usn=f"{udn}::urn:lge-com:service:webos-second-screen:1",
        upnp={
            ATTR_UPNP_UDN: udn,
            ATTR_UPNP_FRIENDLY_NAME: name,
            "st": "urn:lge-com:service:webos-second-screen:1",
        },
    )


@pytest.fixture(autouse=True)
def _runtime_factory(tv: TVSimulator) -> Any:
    """Keep the runtime client factory mocked for the whole test.

    Entry-creating flows (and reauth reloads) set the entry up in a
    background task that outlives the flow call, so the patch must span
    the entire test, not just the configure step.
    """
    with patch_client_factory(tv):
        yield


@pytest.fixture
def pairing_client(tv: TVSimulator) -> Any:
    """A fresh PROMPT-pairing client whose key appears on connect."""
    client = tv.create_client(HOST, client_key=None)

    async def connect_and_pair() -> None:
        client._connected = True  # noqa: SLF001 - pair accepted on the TV
        client.client_key = "fresh-key"

    client.connect = connect_and_pair  # type: ignore[method-assign]
    return client


@pytest.fixture
def pair(pairing_client: Any) -> Any:
    """Patch the config-flow pairing factory."""
    return patch(
        "custom_components.bscpylgtv.config_flow.make_pairing_client",
        AsyncMock(return_value=pairing_client),
    )


async def submit_user_flow(hass: HomeAssistant, ctx: Any = None) -> Any:
    """Start + submit the user step, returning the pairing-step result."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context=ctx or {"source": "user"}
    )
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )


# ---------------------------------------------------------------------------
# user / pairing
# ---------------------------------------------------------------------------


async def test_user_flow_creates_entry(
    hass: HomeAssistant, pair: Any, tv: TVSimulator
) -> None:
    """Happy path: unique_id=deviceUUID, key+MAC stored, model in title."""
    with pair:
        result = await submit_user_flow(hass)
        assert result["step_id"] == "pairing"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    assert result["title"] == "LG WebOS TV OLED55C2"
    entry = result["result"]
    assert entry.unique_id == UUID
    assert entry.data == {
        CONF_HOST: HOST,
        CONF_CLIENT_KEY: "fresh-key",
        CONF_MAC: tv.mac,
    }
    # The pairing client was disconnected after capturing the result.
    assert not tv.clients[0].is_connected()
    assert tv.clients[0].client_key == "fresh-key"


async def test_user_flow_error_pairing(
    hass: HomeAssistant, pairing_client: Any
) -> None:
    """A rejected pairing shows error_pairing and recovers on resubmit."""
    pairing_client.connect = AsyncMock(side_effect=PyLGTVPairException("denied"))  # type: ignore[method-assign]
    with patch(
        "custom_components.bscpylgtv.config_flow.make_pairing_client",
        AsyncMock(return_value=pairing_client),
    ):
        result = await submit_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["type"] == "form"
        assert result["step_id"] == "pairing"
        assert result["errors"] == {"base": "error_pairing"}

        # The TV accepts on the retry.
        pairing_client.connect = AsyncMock(return_value=None)  # type: ignore[method-assign]
        pairing_client.client_key = "fresh-key"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    assert result["data"][CONF_CLIENT_KEY] == "fresh-key"


@pytest.mark.parametrize(
    "exc",
    [OSError("unreachable"), TimeoutError("too slow")],
    ids=["oserror", "timeout"],
)
async def test_user_flow_cannot_connect(
    hass: HomeAssistant, pairing_client: Any, exc: Exception
) -> None:
    """Connection failures map to cannot_connect (incl. timeout)."""
    pairing_client.connect = AsyncMock(side_effect=exc)  # type: ignore[method-assign]
    with patch(
        "custom_components.bscpylgtv.config_flow.make_pairing_client",
        AsyncMock(return_value=pairing_client),
    ):
        result = await submit_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_missing_device_uuid(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A hello without deviceUUID is not trustworthy: error_pairing."""
    tv.hello_info = {}
    client = tv.create_client(HOST, client_key="fresh-key")
    client._connected = True  # noqa: SLF001
    with patch(
        "custom_components.bscpylgtv.config_flow.make_pairing_client",
        AsyncMock(return_value=client),
    ):
        result = await submit_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "form"
    assert result["errors"] == {"base": "error_pairing"}


async def test_user_flow_duplicate_host_aborts(hass: HomeAssistant, pair: Any) -> None:
    """A second flow for the same host aborts already_configured."""
    build_mock_config_entry(hass, host=HOST, client_key="k1")
    with pair:
        result = await submit_user_flow(hass)
    # The pairing step aborts immediately for a duplicate host.
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# ssdp discovery
# ---------------------------------------------------------------------------


async def test_ssdp_flow_creates_entry(
    hass: HomeAssistant, pair: Any, tv: TVSimulator
) -> None:
    """UDN (uuid: stripped) is the unique_id; '[LG]' cleaned in the name."""
    with pair:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "ssdp"}, data=ssdp_info()
        )
        # Straight through to pairing (host already known).
        assert result["step_id"] == "pairing"
        flow = hass.config_entries.flow.async_progress_by_handler(DOMAIN)[0]
        assert flow["context"]["title_placeholders"] == {"name": "LG webOS TV OLED55C2"}
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    # SSDP-sourced flow keeps the discovered friendly name as the title
    # ("[LG]" stripped); the user flow falls back to DEFAULT_NAME+model.
    assert result["title"] == "LG webOS TV OLED55C2"
    assert result["result"].unique_id == UUID


async def test_ssdp_flow_already_in_progress(hass: HomeAssistant, pair: Any) -> None:
    """A second discovery flow for the same host aborts."""
    with pair:
        first = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "ssdp"}, data=ssdp_info()
        )
        second = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "ssdp"}, data=ssdp_info()
        )
    assert first["type"] == "form"
    assert second["type"] == "abort"
    assert second["reason"] == "already_in_progress"


async def test_ssdp_host_update_on_rediscovery(
    hass: HomeAssistant, pair: Any, tv: TVSimulator
) -> None:
    """A re-discovered TV on a new IP updates the existing entry host."""
    build_mock_config_entry(hass, host="192.168.1.99", unique_id=UUID)
    with pair:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "ssdp"}, data=ssdp_info(host="192.168.1.42")
        )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data[CONF_HOST] == "192.168.1.42"


# ---------------------------------------------------------------------------
# reauth
# ---------------------------------------------------------------------------


async def _start_reauth(hass: HomeAssistant, entry: Any) -> Any:
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
            "title_placeholders": {"name": entry.title},
        },
        data=entry.data,
    )


async def test_reauth_success(hass: HomeAssistant, tv: TVSimulator, pair: Any) -> None:
    """Re-pairing updates the entry key and reloads it."""
    entry = build_mock_config_entry(hass, host=HOST, client_key="stale-key")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    with pair:
        result = await _start_reauth(hass, entry)
        assert result["step_id"] == "reauth_confirm"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_CLIENT_KEY] == "fresh-key"
    # The reauth success triggers an entry reload; wait for it to finish.
    await hass.async_block_till_done()
    assert entry.state.value == "loaded"


async def test_reauth_failure_shows_error(
    hass: HomeAssistant, pair: Any, tv: TVSimulator
) -> None:
    """A failing re-pair shows error_pairing and keeps the old key."""
    entry = build_mock_config_entry(hass, host=HOST, client_key="stale-key")
    with patch(
        "custom_components.bscpylgtv.config_flow.make_pairing_client",
        AsyncMock(side_effect=OSError("tv off")),
    ):
        result = await _start_reauth(hass, entry)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.data[CONF_CLIENT_KEY] == "stale-key"


# ---------------------------------------------------------------------------
# reconfigure
# ---------------------------------------------------------------------------


async def _start_reconfigure(hass: HomeAssistant, entry: Any) -> Any:
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
            "unique_id": entry.unique_id,
        },
    )


def _runtime_client(
    tv: TVSimulator, *, uuid: str = UUID, key: str = "stored-key"
) -> Any:
    """A connected runtime client with a working stored key."""
    client = tv.create_client(HOST, client_key=key)
    client._connected = True  # noqa: SLF001
    tv.hello_info = {"deviceUUID": uuid}
    tv.device_uuid = uuid
    return client


async def test_reconfigure_same_device(hass: HomeAssistant, tv: TVSimulator) -> None:
    """Host change for the same TV updates data, keeps unique_id."""
    entry = build_mock_config_entry(hass, host="192.168.1.99", client_key="stored-key")
    client = _runtime_client(tv)
    with patch(
        "custom_components.bscpylgtv.config_flow.make_runtime_client",
        AsyncMock(return_value=client),
    ):
        result = await _start_reconfigure(hass, entry)
        assert result["step_id"] == "reconfigure"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: HOST}
        )
        await hass.async_block_till_done()
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == HOST
    assert entry.unique_id == UUID


async def test_reconfigure_wrong_device(hass: HomeAssistant, tv: TVSimulator) -> None:
    """A different TV at the new host aborts wrong_device."""
    entry = build_mock_config_entry(hass, host="192.168.1.99", client_key="stored-key")
    client = _runtime_client(tv, uuid="00000000-other-tv-uuid")
    with patch(
        "custom_components.bscpylgtv.config_flow.make_runtime_client",
        AsyncMock(return_value=client),
    ):
        result = await _start_reconfigure(hass, entry)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: HOST}
        )
        await hass.async_block_till_done()
    assert result["type"] == "abort"
    assert result["reason"] == "wrong_device"


async def test_reconfigure_adopts_legacy_ip_unique_id(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A v1 IP-based unique_id is adopted as the device UUID."""
    entry = build_mock_config_entry(
        hass, host="192.168.1.99", client_key="stored-key", unique_id="192.168.1.99"
    )
    client = _runtime_client(tv)
    with patch(
        "custom_components.bscpylgtv.config_flow.make_runtime_client",
        AsyncMock(return_value=client),
    ):
        result = await _start_reconfigure(hass, entry)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: HOST}
        )
        await hass.async_block_till_done()
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == UUID


async def test_reconfigure_stale_key_repair(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A stale stored key (commands fail) re-pairs from scratch."""
    entry = build_mock_config_entry(hass, host="192.168.1.99", client_key="stale-key")
    stale = _runtime_client(tv, key="stale-key")
    # The key survives registration but every real command fails.
    stale.get_system_info = AsyncMock(side_effect=OSError("stale key"))  # type: ignore[method-assign]
    fresh = tv.create_client(HOST, client_key=None)
    fresh._connected = True  # noqa: SLF001

    async def connect_and_pair() -> None:
        fresh.client_key = "fresh-key"

    fresh.connect = connect_and_pair  # type: ignore[method-assign]

    with (
        patch(
            "custom_components.bscpylgtv.config_flow.make_runtime_client",
            AsyncMock(return_value=stale),
        ),
        patch(
            "custom_components.bscpylgtv.config_flow.make_pairing_client",
            AsyncMock(return_value=fresh),
        ),
    ):
        result = await _start_reconfigure(hass, entry)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: HOST}
        )
        await hass.async_block_till_done()
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_CLIENT_KEY] == "fresh-key"


async def test_reconfigure_cannot_connect(hass: HomeAssistant, tv: TVSimulator) -> None:
    """An unreachable host shows cannot_connect."""
    entry = build_mock_config_entry(hass, host="192.168.1.99", client_key="stored-key")
    with (
        patch(
            "custom_components.bscpylgtv.config_flow.make_runtime_client",
            AsyncMock(side_effect=OSError("no route")),
        ),
        patch(
            "custom_components.bscpylgtv.config_flow.make_pairing_client",
            AsyncMock(side_effect=OSError("no route")),
        ),
    ):
        result = await _start_reconfigure(hass, entry)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: HOST}
        )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


# ---------------------------------------------------------------------------
# options flow
# ---------------------------------------------------------------------------


def _form_sources(schema: Any) -> list[str]:
    """Extract the multi-select choices from the sources schema key."""
    import voluptuous as vol

    for key in schema.schema:
        if getattr(key, "schema", None) == CONF_SOURCES:
            assert isinstance(key, vol.Optional)
            return key.description["suggested_value"]
    raise AssertionError("sources key not found")


async def _open_options(hass: HomeAssistant, entry: Any) -> Any:
    return await hass.config_entries.options.async_init(entry.entry_id)


async def test_options_live_sources_and_preselect(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """Live source list; stored options are preselected."""
    entry = build_mock_config_entry(
        hass, host=HOST, options={CONF_SOURCES: ["Netflix"]}
    )
    client = _runtime_client(tv)
    with patch(
        "custom_components.bscpylgtv.config_flow.make_runtime_client",
        AsyncMock(return_value=client),
    ):
        result = await _open_options(hass, entry)
    assert result["type"] == "form"
    assert result["step_id"] == "init"
    # Live TV is synthesized; apps + inputs merged by title/label.
    assert _form_sources(result["data_schema"]) == ["Netflix"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SOURCES: ["YouTube", "HDMI 1"], CONF_MAC: ""}
    )
    assert result["type"] == "create_entry"
    assert entry.options == {CONF_SOURCES: ["YouTube", "HDMI 1"]}
    # Drain the OptionsFlowWithReload task so teardown cannot cancel a
    # pending config-entry reload mid-setup.
    await hass.async_block_till_done()
    # Live client disconnected after the read.
    assert not client.is_connected()


async def test_options_persists_mac(hass: HomeAssistant, tv: TVSimulator) -> None:
    """A manual MAC lands in entry.data (not options)."""
    # The reload (OptionsFlowWithReload) re-connects and self-heals the
    # MAC from software_info; align it with the manual value so the
    # assertion observes the OPTIONS write, not the self-heal.
    tv.software_info = {**tv.software_info, "device_id": "11:22:33:44:55:66"}
    entry = build_mock_config_entry(hass, host=HOST)
    client = _runtime_client(tv)
    with patch(
        "custom_components.bscpylgtv.config_flow.make_runtime_client",
        AsyncMock(return_value=client),
    ):
        result = await _open_options(hass, entry)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_SOURCES: ["YouTube"], CONF_MAC: "11:22:33:44:55:66"},
        )
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert entry.data[CONF_MAC] == "11:22:33:44:55:66"
    assert CONF_MAC not in entry.options


async def test_options_clears_mac(hass: HomeAssistant, tv: TVSimulator) -> None:
    """Submitting an empty MAC field removes a stored MAC."""
    # No MAC-shaped device_id → the reload's self-heal cannot re-add it.
    tv.software_info = {**tv.software_info, "device_id": "webos-device"}
    entry = build_mock_config_entry(hass, host=HOST, mac="11:22:33:44:55:66")
    client = _runtime_client(tv)
    with patch(
        "custom_components.bscpylgtv.config_flow.make_runtime_client",
        AsyncMock(return_value=client),
    ):
        result = await _open_options(hass, entry)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SOURCES: ["YouTube"], CONF_MAC: ""}
        )
        await hass.async_block_till_done()
    assert CONF_MAC not in entry.data


async def test_options_invalid_mac_keeps_data(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A malformed MAC shows the field-level invalid_mac error."""
    entry = build_mock_config_entry(hass, host=HOST, mac="11:22:33:44:55:66")
    client = _runtime_client(tv)
    with patch(
        "custom_components.bscpylgtv.config_flow.make_runtime_client",
        AsyncMock(return_value=client),
    ):
        result = await _open_options(hass, entry)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SOURCES: ["YouTube"], CONF_MAC: "nope"}
        )
    assert result["type"] == "form"
    assert result["errors"] == {CONF_MAC: "invalid_mac"}
    assert entry.data[CONF_MAC] == "11:22:33:44:55:66"


async def test_options_degraded_snapshot_on_connect_error(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """An unreachable TV degrades to the coordinator snapshot + error."""
    entry = build_mock_config_entry(hass, host=HOST)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    with patch(
        "custom_components.bscpylgtv.config_flow.make_runtime_client",
        AsyncMock(side_effect=OSError("tv off")),
    ):
        result = await _open_options(hass, entry)
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}
    assert _form_sources(result["data_schema"]) == [
        "YouTube",
        "Live TV",
        "Netflix",
        "HDMI 1",
        "HDMI 2",
    ]


async def test_options_pairing_error_degrades(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A rejected key degrades to the snapshot with error_pairing."""
    entry = build_mock_config_entry(hass, host=HOST)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    with patch(
        "custom_components.bscpylgtv.config_flow.make_runtime_client",
        AsyncMock(side_effect=PyLGTVPairException("rejected")),
    ):
        result = await _open_options(hass, entry)
    assert result["errors"] == {"base": "error_pairing"}


async def test_options_snapshot_empty_when_not_loaded(hass: HomeAssistant) -> None:
    """A not-loaded entry has no snapshot: the list is empty."""
    entry = build_mock_config_entry(hass, host=HOST)
    with patch(
        "custom_components.bscpylgtv.config_flow.make_runtime_client",
        AsyncMock(side_effect=OSError("tv off")),
    ):
        result = await _open_options(hass, entry)
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}
    assert _form_sources(result["data_schema"]) == []


async def test_options_sources_cached_across_invalid_mac(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """A validation error must not trigger a second TV connect."""
    entry = build_mock_config_entry(hass, host=HOST)
    client = _runtime_client(tv)
    factory = AsyncMock(return_value=client)
    with patch("custom_components.bscpylgtv.config_flow.make_runtime_client", factory):
        result = await _open_options(hass, entry)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SOURCES: ["YouTube"], CONF_MAC: "bad"}
        )
        assert result["type"] == "form"
        # Resubmit with the fixed MAC: no additional connect happened.
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_SOURCES: ["YouTube"], CONF_MAC: "11:22:33:44:55:66"},
        )
    assert factory.await_count == 1
    assert result["type"] == "create_entry"
    # Drain the scheduled OptionsFlowWithReload task (see above).
    await hass.async_block_till_done()
