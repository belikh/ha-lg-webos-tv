"""Support for LG WebOS TV remote."""
from __future__ import annotations

import logging
from typing import Any
from collections.abc import Iterable

from homeassistant.components.remote import (
    RemoteEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BscpylgtvConfigEntry
from .entity import BscpylgtvEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: BscpylgtvConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LG WebOS TV remote."""
    async_add_entities([BscpylgtvRemote(entry)])

class BscpylgtvRemote(BscpylgtvEntity, RemoteEntity):
    """Representation of an LG WebOS TV remote."""

    _attr_name = "Remote"

    def __init__(self, entry: BscpylgtvConfigEntry) -> None:
        """Initialize the entity."""
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_remote"

    @property
    def is_on(self) -> bool:
        """Return true if device is on."""
        return self._client.is_connected()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the device on."""
        await self._client.power_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the device off."""
        await self._client.power_off()

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        """Send commands to a device."""
        for cmd in command:
            # Map common HA commands to WebOS keys
            key_map = {
                "HOME": "HOME",
                "MENU": "MENU",
                "UP": "UP",
                "DOWN": "DOWN",
                "LEFT": "LEFT",
                "RIGHT": "RIGHT",
                "SELECT": "ENTER",
                "BACK": "BACK",
                "EXIT": "EXIT",
                "INFO": "INFO",
                "VOLUME_UP": "VOLUMEUP",
                "VOLUME_DOWN": "VOLUMEDOWN",
                "MUTE": "MUTE",
                "POWER": "POWER",
            }

            webos_key = key_map.get(cmd.upper(), cmd)

            try:
                # Use input_button for keys
                if webos_key == "ENTER":
                    await self._client.send_enter_key()
                else:
                    await self._client.input_button(webos_key)

            except Exception as e:
                _LOGGER.warning(f"Failed to send command {cmd}: {e}")
