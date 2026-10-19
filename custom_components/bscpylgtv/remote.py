"""Remote entity for the LG WebOS TV (bscpylgtv) integration.

Plan AD-16: one remote per TV exposing every library button
(``bscpylgtv.buttons.BUTTONS``, 77 entries) plus HA-style aliases and
the virtual pointer/IME commands CLICK / MOVE / SCROLL / TEXT. Buttons
are sent through ``client.button(name)`` — never ``input_button()``
(which takes no arguments in bscpylgtv 0.5.3).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any, override

from homeassistant.components.remote import RemoteEntity, RemoteEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    BUTTONS,
    CONF_MAC,
    DOMAIN,
    LIVE_TV_APP_ID,
    LOGGER,
    REMOTE_BUTTON_ALIASES,
)
from .coordinator import BscpylgtvConfigEntry
from .entity import BscpylgtvEntity, cmd
from .media_player import _async_send_wol

PARALLEL_UPDATES = 0

# MOVE:<dx>,<dy>[,<down>] and SCROLL:<dx>,<dy> — integer pointer deltas.
_MOVE_PATTERN = re.compile(r"^MOVE:(-?\d+),(-?\d+)(?:,(-?\d+))?$")
_SCROLL_PATTERN = re.compile(r"^SCROLL:(-?\d+),(-?\d+)$")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BscpylgtvConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the remote platform."""
    async_add_entities([BscpylgtvRemote(entry)])


class BscpylgtvRemote(BscpylgtvEntity, RemoteEntity):
    """Representation of an LG WebOS TV remote."""

    _attr_supported_features = RemoteEntityFeature.ACTIVITY
    _attr_translation_key = "remote"

    def __init__(self, entry: BscpylgtvConfigEntry) -> None:
        """Initialize the remote entity."""
        super().__init__(entry)
        self._attr_unique_id = f"{entry.unique_id}_remote"

    @property
    @override
    def is_on(self) -> bool:
        """Return True if the device is on.

        Art-standby ("Screen Off") counts as on, mirroring the media
        player state semantics: the socket stays alive and the remote
        can wake the screen over SSAP.
        """
        return self.client.is_on

    @property
    @override
    def current_activity(self) -> str | None:
        """Return the current activity (the current source title)."""
        current = self.client.current_appId
        if current is None:
            return None
        if current in self.client.inputs:
            return self.client.inputs[current].get("label")
        if current in self.client.apps:
            return self.client.apps[current].get("title")
        if current == LIVE_TV_APP_ID:
            return "Live TV"
        return current

    def _unknown_button_error(self, command: str) -> ServiceValidationError:
        """Build the translated error for an unrecognised command."""
        return ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_button",
            translation_placeholders={"button": command},
        )

    async def _async_send_single_command(self, command: str) -> None:
        """Send one command: a virtual, an alias, or a library button."""
        raw = command.strip()
        name = raw.upper()

        if name == "CLICK":
            await self.client.click()
            return
        if name.startswith("MOVE:"):
            if (match := _MOVE_PATTERN.fullmatch(name)) is None:
                raise self._unknown_button_error(command)
            dx, dy, down = match.groups()
            await self.client.move(int(dx), int(dy), int(down or 0))
            return
        if name.startswith("SCROLL:"):
            if (match := _SCROLL_PATTERN.fullmatch(name)) is None:
                raise self._unknown_button_error(command)
            dx, dy = match.groups()
            await self.client.scroll(int(dx), int(dy))
            return
        if name.startswith("TEXT:"):
            # Case is preserved from the raw command (not uppercased).
            if not (text := raw[5:]):
                raise self._unknown_button_error(command)
            await self.client.insert_text(text)
            return

        button = REMOTE_BUTTON_ALIASES.get(name, name)
        if button not in BUTTONS:
            raise self._unknown_button_error(command)
        await self.client.button(button)

    @cmd
    @override
    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        """Send one or more commands to the device."""
        for single in command:
            await self._async_send_single_command(single)

    @cmd
    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the device on.

        In art-standby (on, screen off) the screen is woken over SSAP;
        a fully powered-off TV is woken with a WOL magic packet (AD-8)
        and the coordinator watchdog is poked so the reconnect happens
        as soon as the TV boots.
        """
        if self.client.is_on:
            if not self.client.is_screen_on:
                await self.client.turn_screen_on()
            return
        mac = self._entry.data.get(CONF_MAC)
        if mac is None:
            LOGGER.warning(
                "Cannot turn on %s: no MAC address configured for"
                " wake-on-lan (set it in the integration options)",
                self._entry.title,
            )
            return
        await _async_send_wol(self.hass, mac)
        self.hass.async_create_task(self.coordinator.async_request_refresh())

    @cmd
    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the device off (art-standby, same as the media player)."""
        await self.client.turn_screen_off()
