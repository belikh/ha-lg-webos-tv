"""Support for LG WebOS TV buttons."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from bscpylgtv import WebOsClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

BUTTON_TYPES = [
    ("reboot", "Reboot", "mdi:restart", EntityCategory.CONFIG),
    ("reboot_soft", "Soft Reboot", "mdi:restart", EntityCategory.CONFIG),
    ("turn_screen_off", "Turn Screen Off", "mdi:television-off", None),
    ("turn_screen_on", "Turn Screen On", "mdi:television", None),
    ("show_screen_saver", "Screensaver", "mdi:image", None),
    ("take_screenshot", "Take Screenshot", "mdi:camera", None),
    ("enable_tpc_or_gsr_tpc_on", "Enable TPC", "mdi:check", EntityCategory.CONFIG),
    ("enable_tpc_or_gsr_tpc_off", "Disable TPC", "mdi:close", EntityCategory.CONFIG),
    ("enable_tpc_or_gsr_gsr_on", "Enable GSR", "mdi:check", EntityCategory.CONFIG),
    ("enable_tpc_or_gsr_gsr_off", "Disable GSR", "mdi:close", EntityCategory.CONFIG),
]

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LG WebOS TV buttons."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for key, name, icon, category in BUTTON_TYPES:
        entities.append(BscpylgtvButton(coordinator, entry, key, name, icon, category))

    async_add_entities(entities)


class BscpylgtvButton(ButtonEntity):
    """Representation of an LG WebOS TV button."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key, name, icon, category):
        """Initialize the entity."""
        self._coordinator = coordinator
        self._client: WebOsClient = coordinator.client
        self._key = key
        self._attr_name = name
        self._attr_icon = icon
        self._attr_entity_category = category
        self._attr_unique_id = f"{entry.data[CONF_IP_ADDRESS]}_button_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_IP_ADDRESS])},
            name=entry.title,
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        if self._key == "reboot":
            await self._client.reboot()
        elif self._key == "reboot_soft":
            await self._client.reboot_soft()
        elif self._key == "turn_screen_off":
            await self._client.turn_screen_off()
        elif self._key == "turn_screen_on":
            await self._client.turn_screen_on()
        elif self._key == "show_screen_saver":
            await self._client.show_screen_saver()
        elif self._key == "take_screenshot":
            await self._client.take_screenshot()
        elif self._key == "enable_tpc_or_gsr_tpc_on":
            await self._client.enable_tpc_or_gsr("tpc", True)
        elif self._key == "enable_tpc_or_gsr_tpc_off":
            await self._client.enable_tpc_or_gsr("tpc", False)
        elif self._key == "enable_tpc_or_gsr_gsr_on":
            await self._client.enable_tpc_or_gsr("gsr", True)
        elif self._key == "enable_tpc_or_gsr_gsr_off":
            await self._client.enable_tpc_or_gsr("gsr", False)
