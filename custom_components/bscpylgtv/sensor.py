"""Support for LG WebOS TV sensors."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, EntityCategory, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from bscpylgtv import WebOsClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LG WebOS TV sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        WebOsCurrentAppSensor(coordinator, entry),
        WebOsVolumeSensor(coordinator, entry),
        WebOsPowerStateSensor(coordinator, entry),
        WebOsSoftwareInfoSensor(coordinator, entry, "model_name", "Model Name", None, EntityCategory.DIAGNOSTIC),
        WebOsSoftwareInfoSensor(coordinator, entry, "major_ver", "Software Version Major", None, EntityCategory.DIAGNOSTIC),
        WebOsSoftwareInfoSensor(coordinator, entry, "minor_ver", "Software Version Minor", None, EntityCategory.DIAGNOSTIC),
        WebOsSoftwareInfoSensor(coordinator, entry, "device_id", "Device ID", None, EntityCategory.DIAGNOSTIC),
    ]

    async_add_entities(entities)


class WebOsSensor(SensorEntity):
    """Base sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry):
        self._coordinator = coordinator
        self._client: WebOsClient = coordinator.client
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_IP_ADDRESS])},
            name=entry.title,
        )

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.async_on_remove(self._coordinator.async_add_listener(self.async_write_ha_state))


class WebOsCurrentAppSensor(WebOsSensor):
    """Sensor for current app."""

    _attr_name = "Current App"
    _attr_unique_id_suffix = "current_app"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data[CONF_IP_ADDRESS]}_current_app"

    @property
    def native_value(self) -> str | None:
        """Return the current app."""
        app_id = self._client.current_appId
        if not app_id:
             return None

        # Try to resolve to name
        for app in self._client.apps:
            if app.get("id") == app_id:
                return app.get("title")

        return app_id


class WebOsVolumeSensor(WebOsSensor):
    """Sensor for volume."""

    _attr_name = "Volume"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.VOLUME_STORAGE # Or just None
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data[CONF_IP_ADDRESS]}_volume"

    @property
    def native_value(self) -> int | None:
        return self._client.volume


class WebOsPowerStateSensor(WebOsSensor):
    """Sensor for power state."""

    _attr_name = "Power State"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data[CONF_IP_ADDRESS]}_power_state"

    @property
    def native_value(self) -> str | None:
        power_state = self._client.power_state
        if isinstance(power_state, dict):
            return power_state.get("state")
        return str(power_state)


class WebOsSoftwareInfoSensor(WebOsSensor):
    """Sensor for software info fields."""

    def __init__(self, coordinator, entry, key, name, icon, category):
        super().__init__(coordinator, entry)
        self._key = key
        self._attr_name = name
        self._attr_icon = icon
        self._attr_entity_category = category
        self._attr_unique_id = f"{entry.data[CONF_IP_ADDRESS]}_sw_{key}"

    @property
    def native_value(self) -> str | None:
        if self._client.software_info:
            return self._client.software_info.get(self._key)
        return None
