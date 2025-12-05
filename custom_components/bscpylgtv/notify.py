"""Support for LG WebOS TV notifications."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.notify import (
    NotifyEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from bscpylgtv import WebOsClient
from . import BscpylgtvConfigEntry
from .entity import BscpylgtvEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: BscpylgtvConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LG WebOS TV notification entity."""
    async_add_entities([BscpylgtvNotify(entry)])

class BscpylgtvNotify(BscpylgtvEntity, NotifyEntity):
    """Representation of an LG WebOS TV notification entity."""

    _attr_name = "Notify"

    def __init__(self, entry: BscpylgtvConfigEntry) -> None:
        """Initialize the entity."""
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_notify"

    async def async_send_message(self, message: str, **kwargs: Any) -> None:
        """Send a message."""
        # Use send_message method
        # Usually takes message text.
        await self._client.send_message(message)
