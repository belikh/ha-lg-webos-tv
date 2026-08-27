"""Support for LG WebOS TV media player."""
from __future__ import annotations

import logging
from typing import Any
import voluptuous as vol

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.components import wake_on_lan
from homeassistant.const import CONF_IP_ADDRESS, CONF_MAC
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback, async_get_current_platform

from bscpylgtv import WebOsClient
from . import BscpylgtvConfigEntry
from .entity import BscpylgtvEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: BscpylgtvConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the LG WebOS TV media player."""
    async_add_entities([BscpylgtvMediaPlayer(entry)])

    # Register services
    platform = async_get_current_platform()

    platform.async_register_entity_service(
        "launch_app",
        {vol.Required("app_id"): cv.string},
        "async_launch_app",
    )

    platform.async_register_entity_service(
        "launch_app_with_params",
        {
            vol.Required("app_id"): cv.string,
            vol.Required("params"): dict,
        },
        "async_launch_app_with_params",
    )

    platform.async_register_entity_service(
        "command",
        {
            vol.Required("command"): cv.string,
            vol.Optional("payload"): vol.Any(dict, list, cv.string, int, float, bool),
        },
        "async_command",
    )

    platform.async_register_entity_service(
        "set_settings",
        {
            vol.Required("category"): cv.string,
            vol.Required("settings"): dict,
        },
        "async_set_settings",
    )


class BscpylgtvMediaPlayer(BscpylgtvEntity, MediaPlayerEntity):
    """Representation of an LG WebOS TV media player."""

    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_name = None  # Use device name from device_info

    def __init__(self, entry: BscpylgtvConfigEntry) -> None:
        """Initialize the entity."""
        super().__init__(entry)
        self._attr_unique_id = entry.data[CONF_IP_ADDRESS]

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available or (self._entry.data.get(CONF_MAC) is not None)

    @property
    def state(self) -> MediaPlayerState | None:
        """Return the state of the device."""
        power_state = self._client.power_state
        if not power_state:
             if self._client.is_connected():
                 return MediaPlayerState.ON
             return MediaPlayerState.OFF

        state_str = power_state.get("state", "").lower()
        if state_str in ["active", "on", "turningon", "screenoff"]:
            return MediaPlayerState.ON

        return MediaPlayerState.OFF

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        if self._client.volume:
            return float(self._client.volume) / 100.0
        return None

    @property
    def is_volume_muted(self) -> bool | None:
        """Boolean if volume is currently muted."""
        return self._client.muted

    @property
    def source(self) -> str | None:
        """Name of the current input source."""
        current_app_id = self._client.current_appId
        if not current_app_id:
            return None

        # client.inputs is a dict keyed by appId, client.apps by app id
        inp = self._client.inputs.get(current_app_id)
        if isinstance(inp, dict):
            return inp.get("label")

        app = self._client.apps.get(current_app_id)
        if isinstance(app, dict):
            return app.get("title")

        return current_app_id

    @property
    def source_list(self) -> list[str] | None:
        """List of available input sources."""
        sources = []
        for inp in self._client.inputs.values():
            label = inp.get("label")
            if label:
                sources.append(label)
        for app in self._client.apps.values():
            title = app.get("title")
            if title:
                sources.append(title)
        return sorted(sources)

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Flag media player features that are supported."""
        return (
            MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.SELECT_SOURCE
            | MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.PAUSE
            | MediaPlayerEntityFeature.STOP
            | MediaPlayerEntityFeature.PREVIOUS_TRACK
            | MediaPlayerEntityFeature.NEXT_TRACK
            | MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.PLAY_MEDIA
        )

    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        if mac := self._entry.data.get(CONF_MAC):
            await self.hass.async_add_executor_job(
                wake_on_lan.send_magic_packet, mac
            )
        await self._client.power_on()

    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        await self._client.power_off()

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        await self._client.set_volume(int(volume * 100))

    async def async_volume_up(self) -> None:
        """Volume up the media player."""
        await self._client.volume_up()

    async def async_volume_down(self) -> None:
        """Volume down the media player."""
        await self._client.volume_down()

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        await self._client.set_mute(mute)

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        for inp in self._client.inputs.values():
            if inp.get("label") == source:
                await self._client.set_input(inp.get("id"))
                return

        for app in self._client.apps.values():
            if app.get("title") == source:
                await self._client.launch_app(app.get("id"))
                return

    async def async_media_play(self) -> None:
        """Send play command."""
        await self._client.play()

    async def async_media_pause(self) -> None:
        """Send pause command."""
        await self._client.pause()

    async def async_media_stop(self) -> None:
        """Send stop command."""
        await self._client.stop()

    async def async_media_next_track(self) -> None:
        """Send fast forward command."""
        await self._client.fast_forward()

    async def async_media_previous_track(self) -> None:
        """Send rewind command."""
        await self._client.rewind()

    async def async_play_media(self, media_type: MediaType | str, media_id: str, **kwargs: Any) -> None:
        """Play a piece of media."""
        if media_type == MediaType.APP or media_type == "app":
            await self._client.launch_app(media_id)

    # Service handlers
    async def async_launch_app(self, app_id: str) -> None:
        """Launch app."""
        await self._client.launch_app(app_id)

    async def async_launch_app_with_params(self, app_id: str, params: dict) -> None:
        """Launch app with params."""
        await self._client.launch_app_with_params(app_id, params)

    async def async_command(self, command: str, payload: Any = None) -> None:
        """Send generic command."""
        if not hasattr(self._client, command):
            _LOGGER.error("Command %s not found on WebOsClient", command)
            return

        method = getattr(self._client, command)
        if not callable(method):
            _LOGGER.error("Attribute %s is not callable", command)
            return

        if payload is not None:
             if isinstance(payload, list):
                 await method(*payload)
             elif isinstance(payload, dict):
                 await method(**payload)
             else:
                 await method(payload)
        else:
            await method()

    async def async_set_settings(self, category: str, settings: dict) -> None:
        """Set settings."""
        await self._client.set_settings(category, settings)
