"""The LG WebOS TV (bscpylgtv) integration."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from bscpylgtv import WebOsClient
from .const import DOMAIN, CONF_KEY_FILE, DEFAULT_PING_INTERVAL

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.MEDIA_PLAYER,
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SWITCH,
]

@dataclass
class BscpylgtvData:
    """Runtime data for the integration."""
    client: WebOsClient
    coordinator: WebOsCoordinator

type BscpylgtvConfigEntry = ConfigEntry[BscpylgtvData]

async def async_setup_entry(hass: HomeAssistant, entry: BscpylgtvConfigEntry) -> bool:
    """Set up LG WebOS TV from a config entry."""
    host = entry.data[CONF_IP_ADDRESS]
    key_file_path = entry.data[CONF_KEY_FILE]

    # States to subscribe to
    states = [
        "system_info",
        "software_info",
        "power",
        "current_app",
        "muted",
        "volume",
        "apps",
        "inputs",
        "sound_output",
        "picture_settings"
    ]

    client = await WebOsClient.create(
        host,
        key_file_path=key_file_path,
        ping_interval=DEFAULT_PING_INTERVAL,
        states=states
    )

    try:
        await client.connect()
    except Exception as ex:
        raise ConfigEntryNotReady(f"Unable to connect to {host}: {ex}") from ex

    coordinator = WebOsCoordinator(hass, client)
    await client.register_state_update_callback(coordinator.async_on_state_update)

    # Use runtime_data (modern HA approach)
    entry.runtime_data = BscpylgtvData(client=client, coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: BscpylgtvConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.client.disconnect()

    return unload_ok

class WebOsCoordinator:
    """Coordinator to handle updates from the TV."""

    def __init__(self, hass: HomeAssistant, client: WebOsClient):
        self.hass = hass
        self.client = client
        self._listeners = []

    def async_add_listener(self, update_callback):
        """Add a listener for updates."""
        self._listeners.append(update_callback)
        return lambda: self._listeners.remove(update_callback)

    async def async_on_state_update(self, client):
        """Called when the client receives a state update."""
        for callback in self._listeners:
            if asyncio.iscoroutinefunction(callback):
                await callback()
            else:
                callback()
