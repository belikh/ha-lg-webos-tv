"""Support for LG WebOS TV switches."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from bscpylgtv import WebOsClient
from . import BscpylgtvConfigEntry
from .entity import BscpylgtvEntity

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True, kw_only=True)
class BscpylgtvSwitchEntityDescription(SwitchEntityDescription):
    """Describes LG WebOS TV switch entity."""
    category: str
    setting_key: str # Key in the settings dict

# Only adding one example placeholder as "AI Picture" support varies greatly
SWITCHES: tuple[BscpylgtvSwitchEntityDescription, ...] = (
    # BscpylgtvSwitchEntityDescription(
    #     key="ai_picture_pro",
    #     translation_key="ai_picture_pro",
    #     icon="mdi:auto-fix",
    #     category="aiPicture",
    #     setting_key="ai_Picture"
    # ),
)

async def async_setup_entry(
    hass: HomeAssistant, entry: BscpylgtvConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LG WebOS TV switches."""
    if not SWITCHES:
        return

    async_add_entities(
        BscpylgtvSwitch(entry, description) for description in SWITCHES
    )

class BscpylgtvSwitch(BscpylgtvEntity, SwitchEntity):
    """Representation of an LG WebOS TV switch."""

    entity_description: BscpylgtvSwitchEntityDescription

    def __init__(
        self, entry: BscpylgtvConfigEntry, description: BscpylgtvSwitchEntityDescription
    ) -> None:
        """Initialize the entity."""
        super().__init__(entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        # Reading settings is not always straightforward as we need to know where to look in 'client'
        return None

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        payload = {self.entity_description.setting_key: "on"}
        await self._client.set_settings(self.entity_description.category, payload)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        payload = {self.entity_description.setting_key: "off"}
        await self._client.set_settings(self.entity_description.category, payload)
