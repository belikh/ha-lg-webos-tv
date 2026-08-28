"""Button entities for the LG WebOS TV (bscpylgtv) integration.

Four buttons (plan §3.2): ``turn_screen_off`` / ``turn_screen_on``
(plain), ``screenshot`` (writes a JPG into ``config/www``) and ``reboot``
(CONFIG, disabled by default). The dead v1 buttons ``reboot_soft`` and
``show_screen_saver`` are intentionally gone (plan AD-9: those library
methods are author-documented as non-functional on modern webOS).
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
    ButtonEntityDescription(key="screenshot", translation_key="screenshot"),
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
        elif key == "screenshot":
            await self._async_write_screenshot()
        else:
            await self.client.reboot()

    async def _async_write_screenshot(self) -> None:
        """Capture a screenshot and write it under ``config/www`` (AD-11).

        Delegates to the coordinator's shared implementation (payload
        shapes vary by model — base64 ``image`` on older sets, an
        ``imageUri`` resource on current webOS). Write failures surface
        as the dedicated ``screenshot_write_failed`` error from the
        coordinator rather than a raw ``OSError``.
        """
        await self.coordinator.async_take_screenshot(
            self.hass.config.path("www", f"bscpylgtv_{self._entry.unique_id}.jpg")
        )
