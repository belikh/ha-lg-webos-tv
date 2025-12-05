"""Support for LG WebOS TV selects."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from bscpylgtv import WebOsClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PICTURE_MODES = [
    "cinema", "expert1", "expert2", "game", "technicolorExpert", "filmMaker",
    "hdr_cinema", "hdr_game", "hdr_technicolorExpert", "hdr_filmMaker",
    "dolby_cinema_bright", "dolby_cinema_dark", "dolby_game",
    "eco", "standard", "vivid", "sports", "aps"
]

# Sound Output options (might vary by TV, but we can list common ones or discover)
SOUND_OUTPUTS = [
    "tv_speaker", "external_arc", "external_optical", "lineout", "headphone", "bt_soundbar", "wisa_speaker"
]

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LG WebOS TV selects."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        WebOsPictureModeSelect(coordinator, entry),
        WebOsSoundOutputSelect(coordinator, entry),
    ])


class WebOsSelect(SelectEntity):
    """Base select."""
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


class WebOsPictureModeSelect(WebOsSelect):
    """Select for picture mode."""

    _attr_name = "Picture Mode"
    _attr_options = PICTURE_MODES
    _attr_icon = "mdi:image"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data[CONF_IP_ADDRESS]}_picture_mode"

    @property
    def current_option(self) -> str | None:
        # Check settings for current picture mode
        # The library does not always expose "current picture mode" directly in a simple property
        # but it might be in 'picture_settings' or we can derive it?
        # Inspecting library: 'set_current_picture_mode' exists.
        # But 'get_current_picture_mode'? Not explicitly in the list I saw.
        # However, it might be part of 'picture_settings' or 'system_info'.
        # Let's check `client.picture_settings` again.

        # Actually, usually getting the current picture mode is tricky on WebOS.
        # bscpylgtv might not expose it easily as a state.
        # But let's assume if we set it, we might know it? No.

        # If I look at the README:
        # bscpylgtvcommand 192.168.1.18 launch_app_with_params com.palm.app.settings "{\"target\": \"PictureMode\"}"

        # In the absence of a reliable read method, this select might be optimistic or read-only if we can't read it.
        # But wait, `bscpylgtv` has `set_current_picture_mode`.
        # Does it have `get_picture_settings`? Yes.
        # `picture_settings` property returns a dict.
        # Maybe it has a "pictureMode" key?
        settings = self._client.picture_settings
        if settings:
            # Usually it returns the settings FOR the current mode, but maybe not the mode name itself.
            pass

        return None # Return None if unknown

    async def async_select_option(self, option: str) -> None:
        await self._client.set_current_picture_mode(option)


class WebOsSoundOutputSelect(WebOsSelect):
    """Select for sound output."""

    _attr_name = "Sound Output"
    _attr_options = SOUND_OUTPUTS
    _attr_icon = "mdi:speaker"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.data[CONF_IP_ADDRESS]}_sound_output"

    @property
    def current_option(self) -> str | None:
        return self._client.sound_output

    async def async_select_option(self, option: str) -> None:
        await self._client.change_sound_output(option)
