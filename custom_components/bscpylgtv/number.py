"""Support for LG WebOS TV numbers."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from bscpylgtv import WebOsClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Settings that are numeric
SETTINGS = [
    ("backlight", "Backlight", 0, 100, "mdi:brightness-5"),
    ("contrast", "Contrast", 0, 100, "mdi:contrast"),
    ("brightness", "Brightness", 0, 100, "mdi:brightness-6"),
    ("color", "Color", 0, 100, "mdi:palette"),
    ("sharpness", "Sharpness", 0, 50, "mdi:sharpness"),
    ("oled_light", "OLED Light", 0, 100, "mdi:brightness-7"), # Not all TVs have this
]

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LG WebOS TV numbers."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for key, name, min_val, max_val, icon in SETTINGS:
        entities.append(WebOsSettingNumber(coordinator, entry, key, name, min_val, max_val, icon))

    async_add_entities(entities)


class WebOsSettingNumber(NumberEntity):
    """Representation of an LG WebOS TV number setting."""

    _attr_has_entity_name = True
    _attr_mode = "slider"

    def __init__(self, coordinator, entry, key, name, min_val, max_val, icon):
        """Initialize the entity."""
        self._coordinator = coordinator
        self._client: WebOsClient = coordinator.client
        self._key = key
        self._attr_name = name
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_icon = icon
        self._attr_unique_id = f"{entry.data[CONF_IP_ADDRESS]}_setting_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_IP_ADDRESS])},
            name=entry.title,
        )

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.async_on_remove(self._coordinator.async_add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> float | None:
        """Return the value."""
        # picture_settings is a dict
        settings = self._client.picture_settings
        if settings and self._key in settings:
            try:
                return float(settings[self._key])
            except (ValueError, TypeError):
                return None
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        # We assume "set_settings" works with picture category for these
        # bscpylgtv has set_settings(category, settings)
        # category is usually "picture" for these.
        payload = {self._key: int(value)}
        await self._client.set_settings("picture", payload)
        # Also could use set_current_picture_settings which is safer for current mode
        # await self._client.set_current_picture_settings(payload)
