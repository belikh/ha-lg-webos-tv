"""Support for LG WebOS TV sensors."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from collections.abc import Callable

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from bscpylgtv import WebOsClient
from . import BscpylgtvConfigEntry
from .entity import BscpylgtvEntity

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True, kw_only=True)
class BscpylgtvSensorEntityDescription(SensorEntityDescription):
    """Describes LG WebOS TV sensor entity."""
    value_fn: Callable[[WebOsClient], str | int | float | None]

SENSORS: tuple[BscpylgtvSensorEntityDescription, ...] = (
    BscpylgtvSensorEntityDescription(
        key="current_app",
        translation_key="current_app",
        value_fn=lambda client: client.current_appId,
    ),
    BscpylgtvSensorEntityDescription(
        key="volume",
        translation_key="volume",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda client: client.volume,
    ),
    BscpylgtvSensorEntityDescription(
        key="power_state",
        translation_key="power_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda client: client.power_state.get("state") if isinstance(client.power_state, dict) else str(client.power_state),
    ),
    BscpylgtvSensorEntityDescription(
        key="model_name",
        translation_key="model_name",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda client: client.software_info.get("model_name") if client.software_info else None,
    ),
    BscpylgtvSensorEntityDescription(
        key="major_ver",
        translation_key="major_ver",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda client: client.software_info.get("major_ver") if client.software_info else None,
    ),
    BscpylgtvSensorEntityDescription(
        key="minor_ver",
        translation_key="minor_ver",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda client: client.software_info.get("minor_ver") if client.software_info else None,
    ),
    BscpylgtvSensorEntityDescription(
        key="device_id",
        translation_key="device_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda client: client.software_info.get("device_id") if client.software_info else None,
    ),
)

async def async_setup_entry(
    hass: HomeAssistant, entry: BscpylgtvConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LG WebOS TV sensors."""
    async_add_entities(
        BscpylgtvSensor(entry, description) for description in SENSORS
    )

class BscpylgtvSensor(BscpylgtvEntity, SensorEntity):
    """Representation of an LG WebOS TV sensor."""

    entity_description: BscpylgtvSensorEntityDescription

    def __init__(
        self, entry: BscpylgtvConfigEntry, description: BscpylgtvSensorEntityDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> str | int | float | None:
        """Return the state of the sensor."""
        if self.entity_description.key == "current_app":
            app_id = self._client.current_appId
            if not app_id:
                return None
            for app in self._client.apps:
                if app.get("id") == app_id:
                    return app.get("title")
            return app_id

        return self.entity_description.value_fn(self._client)
