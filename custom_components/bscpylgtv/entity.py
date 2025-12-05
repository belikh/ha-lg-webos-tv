"""Base entity for LG WebOS TV (bscpylgtv)."""
from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.const import CONF_IP_ADDRESS, CONF_MAC
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from . import BscpylgtvConfigEntry, WebOsCoordinator

class BscpylgtvEntity(Entity):
    """Base entity for LG WebOS TV."""

    _attr_has_entity_name = True

    def __init__(self, entry: BscpylgtvConfigEntry) -> None:
        """Initialize the entity."""
        self._entry = entry
        self._client = entry.runtime_data.client
        self._coordinator = entry.runtime_data.coordinator

        # Try to find a unique ID (MAC address)
        # device_id in software_info is often the MAC or UUID
        device_unique_id = entry.data.get(CONF_MAC)
        if not device_unique_id and self._client.software_info:
             device_unique_id = self._client.software_info.get("device_id")

        connections = set()
        if device_unique_id and len(device_unique_id.split(":")) == 6:
            connections.add((dr.CONNECTION_NETWORK_MAC, device_unique_id))

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_IP_ADDRESS])},
            connections=connections,
            name=entry.title,
            manufacturer="LG Electronics",
            model=self._client.system_info.get("modelName") if self._client.system_info else "WebOS TV",
            sw_version=self._client.software_info.get("major_ver") if self._client.software_info else None,
        )

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.async_on_remove(self._coordinator.async_add_listener(self.async_write_ha_state))
