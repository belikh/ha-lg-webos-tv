"""Support for LG WebOS TV numbers."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from bscpylgtv import WebOsClient
from . import BscpylgtvConfigEntry
from .entity import BscpylgtvEntity

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True, kw_only=True)
class BscpylgtvNumberEntityDescription(NumberEntityDescription):
    """Describes LG WebOS TV number entity."""
    category: str = "picture" # Default to picture settings

NUMBERS: tuple[BscpylgtvNumberEntityDescription, ...] = (
    BscpylgtvNumberEntityDescription(
        key="backlight",
        translation_key="backlight",
        native_min_value=0,
        native_max_value=100,
        icon="mdi:brightness-5",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    BscpylgtvNumberEntityDescription(
        key="contrast",
        translation_key="contrast",
        native_min_value=0,
        native_max_value=100,
        icon="mdi:contrast",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    BscpylgtvNumberEntityDescription(
        key="brightness",
        translation_key="brightness",
        native_min_value=0,
        native_max_value=100,
        icon="mdi:brightness-6",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    BscpylgtvNumberEntityDescription(
        key="color",
        translation_key="color",
        native_min_value=0,
        native_max_value=100,
        icon="mdi:palette",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    BscpylgtvNumberEntityDescription(
        key="sharpness",
        translation_key="sharpness",
        native_min_value=0,
        native_max_value=50,
        icon="mdi:sharpness",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    BscpylgtvNumberEntityDescription(
        key="oled_light",
        translation_key="oled_light",
        native_min_value=0,
        native_max_value=100,
        icon="mdi:brightness-7",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)

async def async_setup_entry(
    hass: HomeAssistant, entry: BscpylgtvConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LG WebOS TV numbers."""
    async_add_entities(
        BscpylgtvNumber(entry, description) for description in NUMBERS
    )

class BscpylgtvNumber(BscpylgtvEntity, NumberEntity):
    """Representation of an LG WebOS TV number."""

    entity_description: BscpylgtvNumberEntityDescription
    _attr_mode = "slider"

    def __init__(
        self, entry: BscpylgtvConfigEntry, description: BscpylgtvNumberEntityDescription
    ) -> None:
        """Initialize the entity."""
        super().__init__(entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> float | None:
        """Return the value."""
        settings = self._client.picture_settings
        if settings and self.entity_description.key in settings:
            try:
                return float(settings[self.entity_description.key])
            except (ValueError, TypeError):
                return None
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        payload = {self.entity_description.key: int(value)}
        await self._client.set_settings(self.entity_description.category, payload)
