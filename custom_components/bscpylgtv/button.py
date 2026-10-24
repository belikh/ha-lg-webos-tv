"""Button entities for the LG WebOS TV (bscpylgtv) integration.

Three buttons (plan §3.2): ``turn_screen_off`` / ``turn_screen_on``
(plain) and ``reboot`` (CONFIG, disabled by default). The dead v1
buttons ``reboot_soft`` and ``show_screen_saver`` are intentionally gone
(plan AD-9: those library methods are author-documented as non-functional
on modern webOS). Screenshots are intentionally not offered as a button:
writing them under ``config/www`` exposed them at ``/local/`` without
authentication, so the ``bscpylgtv.take_screenshot`` service is the
supported entry point.
"""

from __future__ import annotations

from typing import override

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BscpylgtvConfigEntry
from .entity import BscpylgtvEntity, cmd

PARALLEL_UPDATES = 0

BUTTONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(key="turn_screen_off", translation_key="turn_screen_off"),
    ButtonEntityDescription(key="turn_screen_on", translation_key="turn_screen_on"),
    ButtonEntityDescription(
        key="reboot",
        translation_key="reboot",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BscpylgtvConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the LG WebOS TV button platform."""
    async_add_entities(BscpylgtvButton(entry, description) for description in BUTTONS)


class BscpylgtvButton(BscpylgtvEntity, ButtonEntity):
    """A button that triggers a one-shot TV command (plan AD-9/AD-11)."""

    entity_description: ButtonEntityDescription

    def __init__(
        self, entry: BscpylgtvConfigEntry, description: ButtonEntityDescription
    ) -> None:
        """Initialize the button."""
        super().__init__(entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"

    @cmd
    @override
    async def async_press(self) -> None:
        """Press the button."""
        key = self.entity_description.key
        if key == "turn_screen_off":
            await self.client.turn_screen_off()
        elif key == "turn_screen_on":
            await self.client.turn_screen_on()
        else:
            await self.client.reboot()
