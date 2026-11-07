"""Diagnostics support for the LG WebOS TV (bscpylgtv) integration."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_UNIQUE_ID
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from bscpylgtv import WebOsClient

from .const import CONF_CLIENT_KEY, DOMAIN
from .coordinator import BscpylgtvConfigEntry, BscpylgtvCoordinator

# webostv diagnostics superset (plan AD-18): the pairing key, every
# network identifier (current host, legacy v1 ip_address, unique_id,
# wake-on-LAN MAC — "mac" in entry.data, "macAddress" in TV payloads)
# and the per-payload fields that leak device identifiers or icons.
TO_REDACT = {
    CONF_CLIENT_KEY,  # "client_key"
    CONF_HOST,  # "host"
    CONF_MAC,  # "mac" (entry.data wake-on-LAN MAC)
    "ip_address",  # legacy v1 entry data key
    CONF_UNIQUE_ID,  # "unique_id"
    "device_id",
    "deviceUUID",
    "macAddress",
    "icon",
    "largeIcon",
    "signature",
    "sessionId",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BscpylgtvConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    integration = await async_get_integration(hass, DOMAIN)
    return async_redact_data(
        {
            "versions": _versions(str(integration.version)),
            "entry": entry.as_dict(),
            "client": _client_snapshot(entry),
        },
        TO_REDACT,
    )


def _versions(integration_version: str) -> dict[str, str | None]:
    """Return the versions a maintainer needs to read a bug report."""
    try:
        library = pkg_version("bscpylgtv")
    except PackageNotFoundError:
        library = None
    return {
        "integration": integration_version,
        "bscpylgtv": library,
        "home_assistant": HA_VERSION,
    }


def _client_snapshot(entry: BscpylgtvConfigEntry) -> dict[str, Any]:
    """Build a count-only client snapshot (plan AD-18).

    Apps, inputs and channels are deliberately reduced to counts: the
    full lists would leak the app catalog and channel lineup. Diagnostics
    can be requested while the entry is not loaded (e.g. after a failed
    setup), so the coordinator access is guarded.
    """
    # getattr: ConfigEntry.runtime_data is an annotation only — the
    # attribute does not exist until a setup assigns it, so reading it
    # directly on a never-loaded entry raises AttributeError.
    coordinator = getattr(entry, "runtime_data", None)
    client: WebOsClient | None = None
    if entry.state is ConfigEntryState.LOADED and coordinator is not None:
        client = coordinator.client

    if client is None:
        return {
            "is_registered": None,
            "is_connected": None,
            "power_state": None,
            "sound_output": None,
            "current_app_id": None,
            "muted": None,
            "volume": None,
            "system_info": None,
            "software_info": None,
            "picture_settings": None,
            "current_channel": None,
            "has_channel": None,
            "channel_retry_running": None,
            "hello_info": None,
            "apps_count": 0,
            "inputs_count": 0,
            "channels_count": 0,
        }

    return {
        "is_registered": client.is_registered(),
        "is_connected": client.is_connected(),
        "power_state": client.power_state,
        "sound_output": client.sound_output,
        # The library property is camelCase (current_appId).
        "current_app_id": client.current_appId,
        "muted": client.muted,
        "volume": client.volume,
        "system_info": client.system_info,
        "software_info": client.software_info,
        "picture_settings": client.picture_settings,
        "current_channel": client.current_channel,
        "has_channel": BscpylgtvCoordinator.has_channel(client),
        "channel_retry_running": coordinator.channel_retry_running,
        "hello_info": client.hello_info,
        "apps_count": len(client.apps or {}),
        "inputs_count": len(client.inputs or {}),
        "channels_count": len(client.channels or []),
    }
