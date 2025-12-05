"""Support for LG WebOS TV switches."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from bscpylgtv import WebOsClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LG WebOS TV switches."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Switches for specific boolean settings could be added here
    # For now, I'll add a dummy switch or investigate what boolean settings are safe/useful.
    # The user asked for "everything".
    # There are settings like "ai_Picture" (AI Picture Pro) inside settings.

    entities = []
    # Example: AI Picture Pro (if we can read it)
    # entities.append(WebOsSettingSwitch(coordinator, entry, "ai_Picture", "AI Picture Pro", "aiPicture", "mdi:auto-fix"))

    async_add_entities(entities)

class WebOsSettingSwitch(SwitchEntity):
    """Switch for a boolean setting."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key, name, category_name, icon):
        self._coordinator = coordinator
        self._client: WebOsClient = coordinator.client
        self._key = key
        self._attr_name = name
        self._category = category_name
        self._attr_icon = icon
        self._attr_unique_id = f"{entry.data[CONF_IP_ADDRESS]}_switch_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_IP_ADDRESS])},
            name=entry.title,
        )

    @property
    def is_on(self) -> bool | None:
        # Check settings
        # This requires knowning where the setting lives.
        return None

    async def async_turn_on(self, **kwargs) -> None:
        payload = {self._key: "on"} # or true
        await self._client.set_settings(self._category, payload)

    async def async_turn_off(self, **kwargs) -> None:
        payload = {self._key: "off"} # or false
        await self._client.set_settings(self._category, payload)
