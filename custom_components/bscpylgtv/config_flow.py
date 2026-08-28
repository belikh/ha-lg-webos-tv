"""Config flow for the LG WebOS TV (bscpylgtv) integration.

Mirrors the HA core webostv flow semantics (plan AD-5): user and
discovery flows pair a fresh PROMPT client (never PIN — the library's
PIN path does blocking ``input()``), reauth re-pairs from scratch, and
reconfigure verifies the same physical device before updating the host.
The options flow (plan AD-6) manages the enabled source list plus the
manual wake-on-LAN MAC fallback.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from collections.abc import Callable, Coroutine, Mapping
from typing import Any, NamedTuple, Self, override
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_MAC
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service_info.ssdp import (
    ATTR_UPNP_FRIENDLY_NAME,
    ATTR_UPNP_UDN,
    SsdpServiceInfo,
)

from bscpylgtv import WebOsClient
from bscpylgtv.exceptions import PyLGTVPairException

from .const import (
    BSCP_CONNECTION_EXCEPTIONS,
    COMMAND_TIMEOUT,
    CONF_CLIENT_KEY,
    CONF_SOURCES,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DEFAULT_NAME,
    DISCONNECT_TIMEOUT,
    DOMAIN,
    LIVE_TV_APP_ID,
    RECONNECT_TIMEOUT,
)
from .coordinator import (
    BscpylgtvConfigEntry,
    make_pairing_client,
    make_runtime_client,
    release_client,
)

# PROMPT pairing waits for a human at the TV: generous, but finite.
_PAIRING_TIMEOUT = 60

# Wake-on-LAN MAC as reported in software_info["device_id"].
_MAC_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

DATA_SCHEMA = vol.Schema({vol.Required(CONF_HOST): cv.string})


def _is_legacy_unique_id(unique_id: str) -> bool:
    """Return True for v1 IP/hostname-shaped unique_ids (plan §7).

    Mirrors ``__init__._needs_unique_id_fix`` (Cluster A); duplicated
    locally because that helper is private to its owning module.
    """
    return "." in unique_id or ":" in unique_id


def _extract_mac(software_info: Mapping[str, Any] | None) -> str | None:
    """Return software_info["device_id"] when it is a valid MAC."""
    device_id = (software_info or {}).get("device_id")
    if isinstance(device_id, str) and _MAC_PATTERN.fullmatch(device_id):
        return device_id
    return None


def _get_sources(apps: Mapping[str, Any], inputs: Mapping[str, Any]) -> list[str]:
    """Construct the source list (app titles, input labels, Live TV).

    webostv ``helpers.get_sources`` pattern, with defensive ``.get``
    access because the degraded path feeds it the coordinator's
    last-known snapshot, which may be partially populated.
    """
    sources: list[str] = []
    found_live_tv = False
    for app in apps.values():
        if (title := app.get("title")) is not None:
            sources.append(title)
        if app.get("id") == LIVE_TV_APP_ID:
            found_live_tv = True
    for source in inputs.values():
        if (label := source.get("label")) is not None:
            sources.append(label)
        if source.get("appId") == LIVE_TV_APP_ID:
            found_live_tv = True
    if not found_live_tv:
        sources.append("Live TV")
    # Preserve order when filtering duplicates.
    return list(dict.fromkeys(sources))


def _entry_data(
    host: str,
    client_key: str | None,
    mac: str | None,
    fallback_mac: str | None = None,
) -> dict[str, Any]:
    """Build entry data; the MAC is stored only when valid."""
    data: dict[str, Any] = {CONF_HOST: host, CONF_CLIENT_KEY: client_key}
    mac = mac or fallback_mac
    if mac:
        data[CONF_MAC] = mac
    return data


async def _async_connect_client(
    client: WebOsClient, connect_timeout: float
) -> WebOsClient:
    """Connect ``client``, abandoning it if the connect fails or wedges."""
    try:
        await asyncio.wait_for(client.connect(), connect_timeout)
    except Exception:  # noqa: BLE001 - release, then let the caller map it
        release_client(client)
        raise
    return client


async def _async_pair(hass: HomeAssistant, host: str) -> WebOsClient:
    """Connect a fresh PROMPT-pairing client (plan AD-2)."""
    client = await make_pairing_client(hass, host)
    return await _async_connect_client(client, _PAIRING_TIMEOUT)


async def _async_connect_with_key(
    hass: HomeAssistant, host: str, client_key: str | None
) -> WebOsClient:
    """Connect a runtime client with the stored key (reconfigure/options)."""
    client = await make_runtime_client(hass, host, client_key)
    return await _async_connect_client(client, RECONNECT_TIMEOUT)


async def _async_disconnect(client: WebOsClient) -> None:
    """Disconnect a healthy client; abandon it if teardown wedges (R-6)."""
    client.clear_state_update_callbacks()
    try:
        await asyncio.wait_for(client.disconnect(), DISCONNECT_TIMEOUT)
    except Exception:  # noqa: BLE001 - never hang a flow on teardown
        release_client(client)


async def _async_best_effort[T](
    fetch: Callable[[], Coroutine[Any, Any, T]],
) -> T | None:
    """Run a bounded info fetch; return None on any failure."""
    with contextlib.suppress(Exception):
        return await asyncio.wait_for(fetch(), COMMAND_TIMEOUT)
    return None


class _PairingResult(NamedTuple):
    """Values captured from a freshly paired client."""

    client_key: str | None
    device_uuid: str
    mac: str | None
    title: str


async def _async_capture_pairing_result(client: WebOsClient) -> _PairingResult:
    """Capture the pairing key, device UUID, MAC and title, then disconnect.

    The pairing client subscribes to no states, so system/software info
    are fetched explicitly (best effort — a failing fetch degrades to
    the default title and no MAC instead of failing the pairing).
    """
    system_info = await _async_best_effort(client.get_system_info)
    software_info = await _async_best_effort(client.get_software_info)
    device_uuid = (client.hello_info or {}).get("deviceUUID")
    title = DEFAULT_NAME
    if model_name := (system_info or {}).get("modelName"):
        title = f"{DEFAULT_NAME} {model_name}"
    await _async_disconnect(client)
    if not device_uuid:
        # connect() validated the hello handshake, so a missing UUID
        # means the pairing exchange was not trustworthy after all.
        raise PyLGTVPairException("TV did not provide a device UUID")
    return _PairingResult(
        client_key=client.client_key,
        device_uuid=device_uuid,
        mac=_extract_mac(software_info),
        title=title,
    )


class BscpylgtvConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the bscpylgtv config flow."""

    VERSION = CONFIG_ENTRY_VERSION
    MINOR_VERSION = CONFIG_ENTRY_MINOR_VERSION

    def __init__(self) -> None:
        """Initialize the flow."""
        self._host: str = ""
        self._name: str = ""

    @staticmethod
    @callback
    @override
    def async_get_options_flow(
        config_entry: BscpylgtvConfigEntry,
    ) -> BscpylgtvOptionsFlow:
        """Return the options flow handler."""
        return BscpylgtvOptionsFlow()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        if user_input is not None:
            self._host = user_input[CONF_HOST]
            return await self.async_step_pairing()

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)

    async def async_step_pairing(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle pairing: submit and accept the prompt on the TV."""
        self._async_abort_entries_match({CONF_HOST: self._host})

        self.context["title_placeholders"] = {"name": self._name}
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                client = await _async_pair(self.hass, self._host)
                result = await _async_capture_pairing_result(client)
            except PyLGTVPairException:
                errors["base"] = "error_pairing"
            except BSCP_CONNECTION_EXCEPTIONS:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(
                    result.device_uuid, raise_on_progress=False
                )
                self._abort_if_unique_id_configured({CONF_HOST: self._host})
                if not self._name:
                    self._name = result.title
                return self.async_create_entry(
                    title=self._name,
                    data=_entry_data(self._host, result.client_key, result.mac),
                )

        return self.async_show_form(step_id="pairing", errors=errors)

    @override
    async def async_step_ssdp(
        self, discovery_info: SsdpServiceInfo
    ) -> ConfigFlowResult:
        """Handle a flow initialized by discovery."""
        assert discovery_info.ssdp_location
        host = urlparse(discovery_info.ssdp_location).hostname
        assert host
        self._host = host
        self._name = discovery_info.upnp.get(
            ATTR_UPNP_FRIENDLY_NAME, DEFAULT_NAME
        ).replace("[LG]", "LG")

        uuid: str = discovery_info.upnp[ATTR_UPNP_UDN]
        assert uuid
        uuid = uuid.removeprefix("uuid:")
        await self.async_set_unique_id(uuid)
        # A re-discovered TV on a new IP updates the existing entry's host.
        self._abort_if_unique_id_configured({CONF_HOST: self._host})

        if self.hass.config_entries.flow.async_has_matching_flow(self):
            return self.async_abort(reason="already_in_progress")

        return await self.async_step_pairing()

    @override
    def is_matching(self, other_flow: Self) -> bool:
        """Return True if other_flow is matching this flow."""
        return other_flow._host == self._host

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon a pairing failure."""
        self._host = entry_data[CONF_HOST]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Re-pair from scratch: the stored key is no longer valid.
                client = await _async_pair(self.hass, self._host)
                result = await _async_capture_pairing_result(client)
            except PyLGTVPairException:
                errors["base"] = "error_pairing"
            except BSCP_CONNECTION_EXCEPTIONS:
                errors["base"] = "cannot_connect"
            else:
                reauth_entry = self._get_reauth_entry()
                data = _entry_data(
                    self._host,
                    result.client_key,
                    result.mac,
                    reauth_entry.data.get(CONF_MAC),
                )
                # The entry unique_id is left untouched: a legacy v1
                # IP-based id is lazily fixed on the next successful
                # setup (plan §7), and a duplicate-UUID entry cannot be
                # resolved by overwriting it here.
                return self.async_update_reload_and_abort(reauth_entry, data=data)

        return self.async_show_form(step_id="reauth_confirm", errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the integration."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            host = user_input[CONF_HOST]
            try:
                client = await self._async_reconfigure_client(
                    host, reconfigure_entry.data.get(CONF_CLIENT_KEY)
                )
                result = await _async_capture_pairing_result(client)
            except PyLGTVPairException:
                errors["base"] = "error_pairing"
            except BSCP_CONNECTION_EXCEPTIONS:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(result.device_uuid)
                stored_unique_id = reconfigure_entry.unique_id
                if (
                    stored_unique_id is not None
                    and stored_unique_id != result.device_uuid
                    and not _is_legacy_unique_id(stored_unique_id)
                ):
                    self._abort_if_unique_id_mismatch(reason="wrong_device")
                data = _entry_data(
                    host,
                    result.client_key,
                    result.mac,
                    reconfigure_entry.data.get(CONF_MAC),
                )
                if stored_unique_id != result.device_uuid:
                    # None or a legacy v1 IP-based unique_id: adopt the
                    # device UUID instead of keeping an unmigratable id.
                    return self.async_update_reload_and_abort(
                        reconfigure_entry,
                        unique_id=result.device_uuid,
                        data=data,
                    )
                return self.async_update_reload_and_abort(reconfigure_entry, data=data)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST, default=reconfigure_entry.data.get(CONF_HOST)
                    ): cv.string,
                }
            ),
            errors=errors,
        )

    async def _async_reconfigure_client(
        self, host: str, client_key: str | None
    ) -> WebOsClient:
        """Return a verified client for reconfigure, re-pairing if needed.

        A stale key can slip through registration (the TV answers the
        pre-registration hello but rejects commands), so the stored-key
        path is verified with a real request before being trusted; when
        it fails, pairing restarts from scratch and the TV shows a fresh
        PROMPT for the user to accept.
        """
        if client_key is not None:
            try:
                client = await _async_connect_with_key(self.hass, host, client_key)
            except PyLGTVPairException:
                pass  # stored key rejected: fall through to fresh pairing
            except BSCP_CONNECTION_EXCEPTIONS:
                raise
            else:
                try:
                    await asyncio.wait_for(client.get_system_info(), COMMAND_TIMEOUT)
                except Exception:  # noqa: BLE001 - stale key or dead link
                    release_client(client)
                else:
                    return client
        return await _async_pair(self.hass, host)


class BscpylgtvOptionsFlow(OptionsFlowWithReload):
    """Handle the options flow (enabled sources + manual MAC)."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._sources: list[str] | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        entry = self.config_entry
        errors: dict[str, str] = {}

        if user_input is not None:
            mac = (user_input.get(CONF_MAC) or "").strip() or None
            if mac is not None and not _MAC_PATTERN.fullmatch(mac):
                errors[CONF_MAC] = "invalid_mac"
            else:
                if mac != entry.data.get(CONF_MAC):
                    data = dict(entry.data)
                    if mac is None:
                        # Clearing the field removes the stored MAC.
                        data.pop(CONF_MAC, None)
                    else:
                        data[CONF_MAC] = mac
                    # Updating entry data from an options flow is allowed;
                    # the reload is triggered by the base class and/or the
                    # data update itself.
                    self.hass.config_entries.async_update_entry(entry, data=data)
                return self.async_create_entry(
                    title="", data={CONF_SOURCES: user_input[CONF_SOURCES]}
                )

        if self._sources is None:
            # Cached across re-shows so a validation error does not
            # trigger a second TV connect.
            self._sources, errors = await self._async_build_sources(entry)

        assert self._sources is not None
        selected = [
            source
            for source in entry.options.get(CONF_SOURCES, [])
            if source in self._sources
        ]
        if not selected:
            selected = self._sources

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SOURCES, description={"suggested_value": selected}
                ): cv.multi_select({source: source for source in self._sources}),
                vol.Optional(
                    CONF_MAC, description={"suggested_value": entry.data.get(CONF_MAC)}
                ): cv.string,
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors or None
        )

    async def _async_build_sources(
        self, entry: BscpylgtvConfigEntry
    ) -> tuple[list[str], dict[str, str]]:
        """Build the live source list, degrading to the last snapshot.

        A live connect with the stored key gives the authoritative
        app/input list; when the TV is unreachable or pairing fails, the
        last coordinator snapshot is used and the connect error is
        surfaced in the form.
        """
        try:
            client = await _async_connect_with_key(
                self.hass, entry.data[CONF_HOST], entry.data.get(CONF_CLIENT_KEY)
            )
        except PyLGTVPairException:
            return self._snapshot_sources(), {"base": "error_pairing"}
        except BSCP_CONNECTION_EXCEPTIONS:
            return self._snapshot_sources(), {"base": "cannot_connect"}
        sources = _get_sources(client.apps, client.inputs)
        await _async_disconnect(client)
        return sources, {}

    def _snapshot_sources(self) -> list[str]:
        """Return sources from the loaded coordinator's last-known state."""
        try:
            client = self.config_entry.runtime_data.client
        except AttributeError:
            # Entry not loaded (setup failed): no snapshot available.
            return []
        return _get_sources(client.apps or {}, client.inputs or {})
