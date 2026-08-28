"""Media player for the LG WebOS TV (bscpylgtv) integration.

Entity per plan AD-10/AD-11: dynamic supported features (volume features
by ``sound_output``, TURN_ON gated on the entry's MAC), title-keyed
source list from the client's ``apps``/``inputs`` dicts, channel
``play_media``, app launching, and the six entity-service mixin methods
(AD-14) that ``services.py`` registers against media player entities.
"""

from __future__ import annotations

import asyncio
import re
import socket
from contextlib import suppress
from http import HTTPStatus
from typing import Any, cast, override

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.const import EntityStateAttribute
from homeassistant.core import HomeAssistant, ServiceResponse, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    ATTR_PAYLOAD,
    ATTR_SOUND_OUTPUT,
    CONF_MAC,
    CONF_SOURCES,
    DOMAIN,
    LIVE_TV_APP_ID,
    LOGGER,
    WOL_PORT,
)
from .coordinator import BscpylgtvConfigEntry
from .entity import BscpylgtvEntity, cmd

PARALLEL_UPDATES = 0

SUPPORT_BSCP = (
    MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.STOP
)

SUPPORT_BSCP_VOLUME = (
    MediaPlayerEntityFeature.VOLUME_MUTE | MediaPlayerEntityFeature.VOLUME_STEP
)

LIVE_TV_APP_NAME = "Live TV"

# Reverse-DNS style app ids ("com.webos.app.livetv", "youtube.2016"). At
# least one letter is required so decimal channel numbers ("5.1") do not
# match.
_APP_ID_PATTERN = re.compile(r"^(?=.*[A-Za-z])[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+$")


def _looks_like_app_id(media_id: str) -> bool:
    """Return True when ``media_id`` is shaped like a full webOS app id."""
    return _APP_ID_PATTERN.fullmatch(media_id) is not None


def _send_wol(mac: str) -> None:
    """Send a wake-on-LAN magic packet (executor only; blocking socket).

    Pattern from lgtv-ha ``_send_wol``: FF x6 + MAC x16, UDP broadcast.
    """
    mac_bytes = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    magic = b"\xff" * 6 + mac_bytes * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(magic, ("<broadcast>", WOL_PORT))


async def _async_send_wol(hass: HomeAssistant, mac: str) -> None:
    """Send a WOL magic packet without blocking the event loop (AD-8)."""
    await hass.async_add_executor_job(_send_wol, mac)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BscpylgtvConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the media player platform."""
    async_add_entities([BscpylgtvMediaPlayer(entry)])


class BscpylgtvMediaPlayer(BscpylgtvEntity, RestoreEntity, MediaPlayerEntity):
    """Representation of an LG WebOS TV media player."""

    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_name = None  # device-named

    def __init__(self, entry: BscpylgtvConfigEntry) -> None:
        """Initialize the media player entity."""
        super().__init__(entry)
        self._attr_unique_id = entry.unique_id
        # Assume that the TV is not paused
        self._paused = False
        self._current_source: str | None = None
        self._source_list: dict[str, dict[str, Any]] = {}
        self._supported_features: MediaPlayerEntityFeature = MediaPlayerEntityFeature(0)
        self._update_supported_features()
        self._update_sources()

    @override
    async def async_added_to_hass(self) -> None:
        """Restore supported features when the TV is off at startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None or self.state != MediaPlayerState.OFF:
            return
        # Restore the persisted feature set minus TURN_ON: the wake path
        # is derived from the entry's MAC on every read instead (webostv
        # does the same to avoid advertising wake before the entry data
        # has been verified).
        features = last_state.attributes.get(EntityStateAttribute.SUPPORTED_FEATURES, 0)
        if isinstance(features, int):
            self._supported_features = (
                MediaPlayerEntityFeature(features) & ~MediaPlayerEntityFeature.TURN_ON
            )

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Refresh derived state before the state is written."""
        self._update_supported_features()
        self._update_sources()
        super()._handle_coordinator_update()

    def _update_supported_features(self) -> None:
        """Recompute the feature set (webostv ``_update_states`` logic).

        Recomputed only while the TV is on (or before the first computed
        set exists); while off the last known set is kept so a restore
        has something meaningful to show.
        """
        client = self.client
        if not client.is_on and self._supported_features:
            return
        supported = SUPPORT_BSCP
        if client.sound_output == "external_speaker":
            # Volume can be stepped/muted but not set absolutely.
            supported |= SUPPORT_BSCP_VOLUME
        elif client.sound_output != "lineout":
            supported |= SUPPORT_BSCP_VOLUME | MediaPlayerEntityFeature.VOLUME_SET
        self._supported_features = supported

    def _update_sources(self) -> None:
        """Rebuild the title -> app/input resolve map (webostv pattern).

        ``apps`` values carry ``id``/``title``; ``inputs`` values carry
        ``appId``/``label``/``id``. The list is filtered through
        ``entry.options[CONF_SOURCES]`` when set, the previous list is
        kept when the TV reports an empty one (it may be off), and
        "Live TV" is synthesized when the app/input dicts don't carry
        the live-tv launch point.
        """
        client = self.client
        source_list = self._source_list
        self._source_list = {}
        conf_sources = self._entry.options.get(CONF_SOURCES)
        found_live_tv = False

        for app in client.apps.values():
            app_id = app.get("id") or ""
            title = app.get("title") or ""
            if app_id == LIVE_TV_APP_ID:
                found_live_tv = True
            if app_id == client.current_appId:
                self._current_source = title
                self._source_list[title] = app
            elif (
                not conf_sources
                or app_id in conf_sources
                or any(word in title for word in conf_sources)
                or any(word in app_id for word in conf_sources)
            ):
                self._source_list[title] = app

        for source in client.inputs.values():
            app_id = source.get("appId") or ""
            label = source.get("label") or ""
            if app_id == LIVE_TV_APP_ID:
                found_live_tv = True
            if app_id == client.current_appId:
                self._current_source = label
                self._source_list[label] = source
            elif (
                not conf_sources
                or label in conf_sources
                or any(word in label for word in conf_sources)
            ):
                self._source_list[label] = source

        # An empty list means the TV may be off: keep the previous list.
        if not self._source_list and source_list:
            self._source_list = source_list
        elif not found_live_tv:
            # Special handling: the live-tv launch point may not appear
            # in the app or input lists.
            app = {"id": LIVE_TV_APP_ID, "title": LIVE_TV_APP_NAME}
            if client.current_appId == LIVE_TV_APP_ID:
                self._current_source = LIVE_TV_APP_NAME
                self._source_list[LIVE_TV_APP_NAME] = app
            elif (
                not conf_sources
                or app["id"] in conf_sources
                or any(word in app["title"] for word in conf_sources)
                or any(word in app["id"] for word in conf_sources)
            ):
                self._source_list[LIVE_TV_APP_NAME] = app

    @property
    @override
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Flag media player features that are supported."""
        if self.coordinator.turn_on_available:
            return self._supported_features | MediaPlayerEntityFeature.TURN_ON
        return self._supported_features

    @property
    @override
    def state(self) -> MediaPlayerState | None:
        """Return the state of the device.

        Documented choice (AD-10): the library treats art-standby
        (power state "Screen Off") as ``is_on`` — the TV keeps its SSAP
        socket alive and can be woken over the network — so this entity
        reports STATE_ON in that state too (matching webostv, where only
        a full power-off is OFF). ``is_screen_on`` distinguishes the
        two for the screen entities (Cluster D).
        """
        if self.client.is_on:
            return MediaPlayerState.ON
        return MediaPlayerState.OFF

    @property
    @override
    def app_id(self) -> str | None:
        """Return the ID of the current running app."""
        return self.client.current_appId

    @property
    @override
    def app_name(self) -> str | None:
        """Return the friendly name of the current running app."""
        current = self.client.current_appId
        if current is None:
            return None
        if current in self.client.apps:
            return self.client.apps[current].get("title")
        if current in self.client.inputs:
            return self.client.inputs[current].get("label")
        if current == LIVE_TV_APP_ID:
            return LIVE_TV_APP_NAME
        return current

    @property
    @override
    def source(self) -> str | None:
        """Return the name of the current input source."""
        return self._current_source

    @property
    @override
    def source_list(self) -> list[str] | None:
        """Return the list of available input sources."""
        return sorted(self._source_list)

    @property
    @override
    def volume_level(self) -> float | None:
        """Return the volume level (0..1)."""
        if (volume := self.client.volume) is None:
            return None
        return float(volume) / 100.0

    @property
    @override
    def is_volume_muted(self) -> bool | None:
        """Return True if volume is currently muted."""
        return self.client.muted

    @property
    @override
    def media_content_type(self) -> MediaType | str | None:
        """Return the content type of the current playing media."""
        if self.client.current_appId == LIVE_TV_APP_ID:
            return MediaType.CHANNEL
        return None

    @property
    @override
    def media_title(self) -> str | None:
        """Return the title of the current playing media (channel name)."""
        if self.client.current_appId == LIVE_TV_APP_ID and (
            channel := self.client.current_channel
        ):
            return channel.get("channelName")
        return None

    @property
    @override
    def media_image_url(self) -> str | None:
        """Return the image URL of the current app (large icon first)."""
        current = self.client.current_appId
        apps = self.client.apps
        if not current or current not in apps:
            return None
        for key in ("largeIcon", "icon"):
            icon = apps[current].get(key)
            if isinstance(icon, str) and icon.startswith("http"):
                return icon
        return None

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the minimal extra state attributes.

        Rebuilt on every state write so the attribute can never go
        stale across client swaps; carries ``sound_output`` only.
        """
        if (sound_output := self.client.sound_output) is None:
            return {}
        return {ATTR_SOUND_OUTPUT: sound_output}

    @override
    async def async_turn_on(self) -> None:
        """Turn the TV on via wake-on-LAN (AD-8).

        SSAP cannot power a TV on (``client.power_on`` is dead on
        modern webOS), so turn_on is a WOL magic packet only, gated on
        the entry's MAC. A watchdog refresh is then scheduled so the
        coordinator reconnects (bounded) once the TV accepts sockets
        and the push state refreshes.
        """
        mac = self._entry.data.get(CONF_MAC)
        if mac is None:
            LOGGER.warning(
                "Cannot turn on %s: no MAC address configured for"
                " wake-on-lan (set it in the integration options)",
                self._entry.title,
            )
            return
        try:
            await _async_send_wol(self.hass, mac)
        except ValueError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={
                    "name": self.coordinator.name,
                    "func": "async_turn_on",
                    "error": f"invalid MAC address {mac!r}",
                },
            ) from err
        # The TV needs seconds to boot; the watchdog keeps retrying the
        # reconnect every SCAN_INTERVAL anyway — this just moves the
        # first attempt forward.
        self.hass.async_create_task(self.coordinator.async_request_refresh())

    @cmd
    @override
    async def async_turn_off(self) -> None:
        """Turn the TV off.

        Follows webostv: ``turn_off`` = ``turn_screen_off`` (active
        art-standby — the SSAP connection stays alive so the TV can be
        interrogated and the screen re-woken remotely).
        """
        await self.client.turn_screen_off()

    @cmd
    @override
    async def async_volume_up(self) -> None:
        """Turn volume up for media player."""
        await self.client.volume_up()

    @cmd
    @override
    async def async_volume_down(self) -> None:
        """Turn volume down for media player."""
        await self.client.volume_down()

    @cmd
    @override
    async def async_set_volume_level(self, volume: float) -> None:
        """Set the volume level, range 0..1.

        The library only clamps at 0, so the 0..100 range is enforced
        integration-side.
        """
        await self.client.set_volume(max(0, min(100, round(volume * 100))))

    @cmd
    @override
    async def async_mute_volume(self, mute: bool) -> None:
        """Send mute command."""
        await self.client.set_mute(mute)

    @cmd
    @override
    async def async_media_play(self) -> None:
        """Send play command."""
        self._paused = False
        await self.client.play()

    @cmd
    @override
    async def async_media_pause(self) -> None:
        """Send pause command."""
        self._paused = True
        await self.client.pause()

    @cmd
    @override
    async def async_media_play_pause(self) -> None:
        """Play or pause the media player."""
        if self._paused:
            await self.async_media_play()
        else:
            await self.async_media_pause()

    @cmd
    @override
    async def async_media_stop(self) -> None:
        """Send stop command."""
        await self.client.stop()

    @cmd
    @override
    async def async_media_next_track(self) -> None:
        """Send next track command (channel up on Live TV)."""
        if self.client.current_appId == LIVE_TV_APP_ID:
            await self.client.channel_up()
        else:
            await self.client.fast_forward()

    @cmd
    @override
    async def async_media_previous_track(self) -> None:
        """Send previous track command (channel down on Live TV)."""
        if self.client.current_appId == LIVE_TV_APP_ID:
            await self.client.channel_down()
        else:
            await self.client.rewind()

    @cmd
    @override
    async def async_select_source(self, source: str) -> None:
        """Select an input source by its title."""
        if (source_dict := self._source_list.get(source)) is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="source_not_found",
                translation_placeholders={"source": source, "name": self.entity_id},
            )
        if source_dict.get("title"):
            await self.client.launch_app(source_dict["id"])
        elif source_dict.get("label"):
            await self.client.set_input(source_dict["id"])

    def _match_channel(self, media_id: str) -> str | None:
        """Resolve a channel by number, exact name or partial name."""
        partial_match_channel_id: str | None = None
        for channel in self.client.channels or []:
            if media_id == channel.get("channelNumber"):
                return channel.get("channelId")
            name = channel.get("channelName") or ""
            if media_id.lower() == name.lower():
                return channel.get("channelId")
            if media_id.lower() in name.lower():
                partial_match_channel_id = partial_match_channel_id or channel.get(
                    "channelId"
                )
        return partial_match_channel_id

    @cmd
    @override
    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play a TV channel or launch an app.

        CHANNEL media resolves against the subscribed channel list
        (exact channelNumber, exact case-insensitive channelName, then
        partial name) and calls ``set_channel(channelId)``. Apps launch
        for an app media type (any case) or when ``media_id`` is a full
        app-id string.
        """
        LOGGER.debug("Call play media type <%s>, Id <%s>", media_type, media_id)
        if str(media_type).lower() == "app" or (
            media_type != MediaType.CHANNEL and _looks_like_app_id(media_id)
        ):
            await self.client.launch_app(media_id)
            return
        if media_type == MediaType.CHANNEL:
            if (channel_id := self._match_channel(media_id)) is not None:
                await self.client.set_channel(channel_id)
                return
            if _looks_like_app_id(media_id):
                await self.client.launch_app(media_id)
                return
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="channel_not_found",
                translation_placeholders={"channel": media_id},
            )
        LOGGER.warning(
            "Unsupported media type <%s> for media id <%s>", media_type, media_id
        )

    @override
    async def _async_fetch_image(self, url: str) -> tuple[bytes | None, str | None]:
        """Fetch artwork from the TV.

        webOS serves self-signed certificates, so certificate
        validation is disabled and the request is bounded to 10 s.
        """
        content = None
        websession = async_get_clientsession(self.hass)
        with suppress(TimeoutError):
            async with asyncio.timeout(10):
                response = await websession.get(url, ssl=False)
                if response.status == HTTPStatus.OK:
                    content = await response.read()
        if content is None:
            LOGGER.warning("Error retrieving proxied image from %s", url)
        return content, None

    # ------------------------------------------------------------------
    # Entity-service mixins (AD-14). services.py registers these as
    # bscpylgtv.* services targeting media player entities.
    # ------------------------------------------------------------------

    @cmd
    async def async_button(self, button: str) -> None:
        """Send a button press (validated against the library's BUTTONS)."""
        try:
            await self.client.button(button)
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_button",
                translation_placeholders={"button": button},
            ) from err

    @cmd
    async def async_command(self, command: str, **kwargs: Any) -> ServiceResponse:
        """Send a raw SSAP request — never getattr dispatch (defect 1)."""
        return await self.client.request(command, payload=kwargs.get(ATTR_PAYLOAD))

    @cmd
    async def async_select_sound_output(self, sound_output: str) -> ServiceResponse:
        """Select the sound output."""
        return await self.client.change_sound_output(sound_output)

    @cmd
    async def async_launch_app(
        self, app_id: str, params: dict[str, Any] | None = None
    ) -> None:
        """Launch an app, optionally with parameters."""
        if params:
            await self.client.launch_app_with_params(app_id, params)
        else:
            await self.client.launch_app(app_id)

    @cmd
    async def async_take_screenshot(
        self, filename: str | None = None
    ) -> ServiceResponse:
        """Take a screenshot (AD-11).

        Delegates to the coordinator's shared implementation, which
        handles every known payload shape (base64 ``image`` on older
        sets, an ``imageUri`` resource on current webOS) and optional
        file writes. Returns ``{"image": <base64 jpg>}``.
        """
        return cast(
            ServiceResponse, await self.coordinator.async_take_screenshot(filename)
        )

    @cmd
    async def async_set_settings(self, category: str, settings: dict[str, Any]) -> None:
        """Set system settings via the Luna path (power-user escape hatch)."""
        await self.client.set_settings(category, settings)
