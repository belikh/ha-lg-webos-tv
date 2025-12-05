"""Support for LG WebOS TV selects."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from collections.abc import Callable, Awaitable

from homeassistant.components.select import (
    SelectEntity,
    SelectEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from bscpylgtv import WebOsClient
from . import BscpylgtvConfigEntry
from .entity import BscpylgtvEntity

_LOGGER = logging.getLogger(__name__)

PICTURE_MODES = [
    "cinema", "expert1", "expert2", "game", "technicolorExpert", "filmMaker",
    "hdr_cinema", "hdr_game", "hdr_technicolorExpert", "hdr_filmMaker",
    "dolby_cinema_bright", "dolby_cinema_dark", "dolby_game",
    "eco", "standard", "vivid", "sports", "aps"
]

# Common sound outputs
SOUND_OUTPUTS = [
    "tv_speaker", "external_arc", "external_optical", "lineout", "headphone", "bt_soundbar", "wisa_speaker"
]

@dataclass(frozen=True, kw_only=True)
class BscpylgtvSelectEntityDescription(SelectEntityDescription):
    """Describes LG WebOS TV select entity."""
    current_fn: Callable[[WebOsClient], str | None]
    select_fn: Callable[[WebOsClient, str], Awaitable[None]]

SELECTS: tuple[BscpylgtvSelectEntityDescription, ...] = (
    BscpylgtvSelectEntityDescription(
        key="picture_mode",
        translation_key="picture_mode",
        icon="mdi:image",
        options=PICTURE_MODES,
        current_fn=lambda client: None, # Reading current mode is unreliable/not directly exposed
        select_fn=lambda client, option: client.set_current_picture_mode(option),
    ),
    BscpylgtvSelectEntityDescription(
        key="sound_output",
        translation_key="sound_output",
        icon="mdi:speaker",
        options=SOUND_OUTPUTS,
        current_fn=lambda client: client.sound_output,
        select_fn=lambda client, option: client.change_sound_output(option),
    ),
)

async def async_setup_entry(
    hass: HomeAssistant, entry: BscpylgtvConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LG WebOS TV selects."""
    async_add_entities(
        BscpylgtvSelect(entry, description) for description in SELECTS
    )

class BscpylgtvSelect(BscpylgtvEntity, SelectEntity):
    """Representation of an LG WebOS TV select."""

    entity_description: BscpylgtvSelectEntityDescription

    def __init__(
        self, entry: BscpylgtvConfigEntry, description: BscpylgtvSelectEntityDescription
    ) -> None:
        """Initialize the entity."""
        super().__init__(entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        return self.entity_description.current_fn(self._client)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.entity_description.select_fn(self._client, option)
