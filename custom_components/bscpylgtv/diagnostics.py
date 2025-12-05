"""Diagnostics support for LG WebOS TV."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_IP_ADDRESS, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant

from . import BscpylgtvConfigEntry

TO_REDACT = {
    CONF_IP_ADDRESS,
    CONF_UNIQUE_ID,
    "device_id", # potentially sensitive
    "deviceUUID",
}

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BscpylgtvConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    client = entry.runtime_data.client

    # Gather relevant info from client
    client_data = {
        "system_info": client.system_info,
        "software_info": client.software_info,
        "power_state": client.power_state,
        "hello_info": client.hello_info,
        "inputs": client.inputs,
        "sound_output": client.sound_output,
        # apps list might be huge, maybe truncate or include count
        "apps_count": len(client.apps) if client.apps else 0,
        "current_app_id": client.current_appId,
        "muted": client.muted,
        "volume": client.volume,
    }

    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "client_data": async_redact_data(client_data, TO_REDACT),
    }
