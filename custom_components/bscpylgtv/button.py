"""Support for LG WebOS TV buttons."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Awaitable

from homeassistant.components.button import (
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from bscpylgtv import WebOsClient
from . import BscpylgtvConfigEntry
from .entity import BscpylgtvEntity

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True, kw_only=True)
class BscpylgtvButtonEntityDescription(ButtonEntityDescription):
    """Describes LG WebOS TV button entity."""
    press_action: Callable[[WebOsClient], Awaitable[None]]

BUTTONS: tuple[BscpylgtvButtonEntityDescription, ...] = (
    BscpylgtvButtonEntityDescription(
        key="reboot",
        translation_key="reboot",
        icon="mdi:restart",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_action=lambda client: client.reboot(),
    ),
    BscpylgtvButtonEntityDescription(
        key="reboot_soft",
        translation_key="reboot_soft",
        icon="mdi:restart",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_action=lambda client: client.reboot_soft(),
    ),
    BscpylgtvButtonEntityDescription(
        key="turn_screen_off",
        translation_key="turn_screen_off",
        icon="mdi:television-off",
        press_action=lambda client: client.turn_screen_off(),
    ),
    BscpylgtvButtonEntityDescription(
        key="turn_screen_on",
        translation_key="turn_screen_on",
        icon="mdi:television",
        press_action=lambda client: client.turn_screen_on(),
    ),
    BscpylgtvButtonEntityDescription(
        key="show_screen_saver",
        translation_key="show_screen_saver",
        icon="mdi:image",
        press_action=lambda client: client.show_screen_saver(),
    ),
    BscpylgtvButtonEntityDescription(
        key="take_screenshot",
        translation_key="take_screenshot",
        icon="mdi:camera",
        press_action=lambda client: client.take_screenshot(),
    ),
    BscpylgtvButtonEntityDescription(
        key="enable_tpc",
        translation_key="enable_tpc",
        icon="mdi:check",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_action=lambda client: client.enable_tpc_or_gsr("tpc", True),
    ),
    BscpylgtvButtonEntityDescription(
        key="disable_tpc",
        translation_key="disable_tpc",
        icon="mdi:close",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_action=lambda client: client.enable_tpc_or_gsr("tpc", False),
    ),
    BscpylgtvButtonEntityDescription(
        key="enable_gsr",
        translation_key="enable_gsr",
        icon="mdi:check",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_action=lambda client: client.enable_tpc_or_gsr("gsr", True),
    ),
    BscpylgtvButtonEntityDescription(
        key="disable_gsr",
        translation_key="disable_gsr",
        icon="mdi:close",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_action=lambda client: client.enable_tpc_or_gsr("gsr", False),
    ),
)

async def async_setup_entry(
    hass: HomeAssistant, entry: BscpylgtvConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LG WebOS TV buttons."""
    async_add_entities(
        BscpylgtvButton(entry, description) for description in BUTTONS
    )

class BscpylgtvButton(BscpylgtvEntity, ButtonEntity):
    """Representation of an LG WebOS TV button."""

    entity_description: BscpylgtvButtonEntityDescription

    def __init__(
        self, entry: BscpylgtvConfigEntry, description: BscpylgtvButtonEntityDescription
    ) -> None:
        """Initialize the entity."""
        super().__init__(entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.entity_description.press_action(self._client)
