"""Select entities for the LG WebOS TV (bscpylgtv) integration.

Three selects (plan AD-13):

* ``picture_mode`` — options from a live enum read once per (re)connect,
  with the curated ``PICTURE_MODES_FALLBACK`` when the TV refuses the
  read (readability varies by model/firmware, plan R-3); never the
  invented v1 list. Writes go through the Luna ``set_settings`` path.
* ``sound_output`` — curated ``SOUND_OUTPUTS`` union the TV's current
  output; current value comes from the subscribed ``sound_output`` push;
  written via ``change_sound_output`` (there is no ``set_sound_output``).
* ``channel`` — fed by the lazily-subscribed ``channels`` list; options
  are rebuilt only when the lineup actually changed (length + first/last
  channelId signature, plan R-5) so 1000+-channel pushes stay cheap.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, override

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from bscpylgtv import WebOsClient

from .const import (
    BSCP_EXCEPTIONS,
    COMMAND_TIMEOUT,
    DOMAIN,
    LOGGER,
    PICTURE_MODES_FALLBACK,
    SOUND_OUTPUTS,
)
from .coordinator import BscpylgtvConfigEntry
from .entity import BscpylgtvEntity, cmd

PARALLEL_UPDATES = 0


def format_channel(channel: Mapping[str, Any]) -> str | None:
    """Format a channel dict as ``"<channelNumber> <channelName>"``.

    Returns the single available component when only one is set, and
    ``None`` when neither is (nothing to display — never a guess).
    """
    parts = [
        str(part)
        for part in (channel.get("channelNumber"), channel.get("channelName"))
        if part not in (None, "")
    ]
    return " ".join(parts) if parts else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BscpylgtvConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the LG WebOS TV select platform."""
    async_add_entities(
        [
            BscpylgtvPictureModeSelect(entry),
            BscpylgtvSoundOutputSelect(entry),
            BscpylgtvChannelSelect(entry),
        ]
    )


class BscpylgtvPictureModeSelect(BscpylgtvEntity, SelectEntity, RestoreEntity):
    """Picture-mode select.

    ``RestoreEntity``: many models (verified on a CX OLED48CXPTA, webOS
    04.40.16) refuse every read of the current ``pictureMode`` — the
    settings service rejects the key, and the config service does not
    carry it — so once written, the last mode is the only value we have.
    Restoring it keeps the select meaningful across HA restarts instead
    of falling back to ``unknown`` after every reboot.
    """

    _attr_translation_key = "picture_mode"

    def __init__(self, entry: BscpylgtvConfigEntry) -> None:
        """Initialize with the curated fallback until a live read lands."""
        super().__init__(entry)
        self._attr_unique_id = f"{entry.unique_id}_picture_mode"
        self._options: list[str] = list(PICTURE_MODES_FALLBACK)
        self._current: str | None = None
        self._read_client: WebOsClient | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last written mode (TVs that block reads never push it)."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in ("unknown", "unavailable"):
            self._current = last.state

    @property
    @override
    def options(self) -> list[str]:
        """Return the option list, with an unknown current appended."""
        options = self._options
        if (current := self.current_option) is not None and current not in options:
            # A mode the fallback doesn't know (firmware-specific enum)
            # must still be selectable/displayable, not silently blanked.
            return [*options, current]
        return options

    @property
    @override
    def current_option(self) -> str | None:
        """Return the current picture mode.

        ``pictureMode`` is not part of the library's pushed subscription
        keys, so the value comes from the per-(re)connect read and the
        optimistic write-back; a future subscription push would win.
        """
        pushed = (self.client.picture_settings or {}).get("pictureMode")
        if isinstance(pushed, str) and pushed:
            return pushed
        return self._current

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Schedule the per-(re)connect enum read, then write state."""
        self._async_schedule_refresh()
        super()._handle_coordinator_update()

    @callback
    def _async_schedule_refresh(self) -> None:
        """Ensure one options read per (re)connected client (plan AD-13).

        Same client-identity guard as the number entities: the read runs
        once per fresh client object, i.e. once per (re)connect.
        """
        client = self.client
        if self._read_client is client or not client.is_connected():
            return
        self._read_client = client
        self.hass.async_create_task(self._async_refresh_options())

    async def _async_refresh_options(self) -> None:
        """Read the live ``pictureMode`` enum; best-effort.

        C2-style responses return the enum list for the key; some models
        answer with the current mode (a plain string) instead, and some
        reject the read entirely (plan R-3) — hence the three shapes.
        """
        if not self.client.is_on:
            # TV went away again; allow a retry on a later update.
            self._read_client = None
            return
        try:
            result = await asyncio.wait_for(
                self.client.get_system_settings("picture", ["pictureMode"]),
                COMMAND_TIMEOUT,
            )
        except BSCP_EXCEPTIONS as ex:
            LOGGER.debug("Live pictureMode read failed; keeping fallback: %s", ex)
            return
        payload = (result.get("settings") or {}).get("pictureMode")
        if isinstance(payload, list) and payload:
            self._options = [str(item) for item in payload]
        else:
            self._options = list(PICTURE_MODES_FALLBACK)
            if isinstance(payload, str) and payload:
                self._current = payload
        self.async_write_ha_state()

    @cmd
    @override
    async def async_select_option(self, option: str) -> None:
        """Set the picture mode through the Luna path (works widely)."""
        await self.client.set_settings("picture", {"pictureMode": option})
        # No push exists for pictureMode; mirror the write optimistically.
        self._current = option
        self.async_write_ha_state()


class BscpylgtvSoundOutputSelect(BscpylgtvEntity, SelectEntity):
    """Sound-output select driven by the subscribed sound_output state."""

    _attr_translation_key = "sound_output"

    def __init__(self, entry: BscpylgtvConfigEntry) -> None:
        """Initialize the sound-output select."""
        super().__init__(entry)
        self._attr_unique_id = f"{entry.unique_id}_sound_output"

    @property
    @override
    def options(self) -> list[str]:
        """Curated outputs unioned with the TV's current output."""
        options = list(SOUND_OUTPUTS)
        if (current := self.client.sound_output) and current not in options:
            options.append(current)
        return options

    @property
    @override
    def current_option(self) -> str | None:
        """Return the current output from the subscribed state."""
        return self.client.sound_output

    @cmd
    @override
    async def async_select_option(self, option: str) -> None:
        """Change the sound output.

        ``change_sound_output`` is the only writer — there is no
        ``set_sound_output`` in the library (webos_client.py). The
        subscribed sound-output push updates the state; the TV confirms
        the change itself, so no optimistic write-back is needed.
        """
        await self.client.change_sound_output(option)


class BscpylgtvChannelSelect(BscpylgtvEntity, SelectEntity):
    """Channel select fed by the lazily-subscribed channel list (AD-13)."""

    _attr_translation_key = "channel"

    def __init__(self, entry: BscpylgtvConfigEntry) -> None:
        """Initialize with an empty lineup; filled once the TV pushes."""
        super().__init__(entry)
        self._attr_unique_id = f"{entry.unique_id}_channel"
        self._options: list[str] = []
        self._channel_ids: dict[str, Any] = {}
        self._option_for_channel_id: dict[Any, str] = {}
        self._signature: tuple[Any, ...] | None = None

    @property
    @override
    def options(self) -> list[str]:
        """Rebuild the option list only when the lineup changed (R-5).

        The TV pushes the full channel list on lineup changes and models
        with 1000+ channels re-push wholesale; rebuilding option state on
        every coordinator update would be needlessly expensive, so the
        cached list is keyed on a length + first/last channelId
        signature (the plan's chosen heuristic — mid-list edits with an
        identical signature surface on the next boundary change).
        """
        channels = self.client.channels or []
        signature = (
            len(channels),
            channels[0].get("channelId") if channels else None,
            channels[-1].get("channelId") if channels else None,
        )
        if signature != self._signature:
            self._signature = signature
            self._options = []
            self._channel_ids = {}
            self._option_for_channel_id = {}
            for channel in channels:
                option = format_channel(channel)
                channel_id = channel.get("channelId")
                if option is None or channel_id is None:
                    continue
                self._options.append(option)
                self._channel_ids[option] = channel_id
                self._option_for_channel_id[channel_id] = option
        return self._options

    @property
    @override
    def current_option(self) -> str | None:
        """Return the option matching the current channel's channelId.

        Matched by channelId (never guessed from the number/name alone);
        ``None`` while no channel is tuned or the list hasn't arrived.
        """
        current = self.client.current_channel
        if not current or (channel_id := current.get("channelId")) is None:
            return None
        return self._option_for_channel_id.get(channel_id)

    @cmd
    @override
    async def async_select_option(self, option: str) -> None:
        """Tune to the channel behind ``option`` by its channelId."""
        _ = self.options  # refresh the resolution cache for the live list
        if (channel_id := self._channel_ids.get(option)) is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="channel_not_found",
                translation_placeholders={"channel": option},
            )
        await self.client.set_channel(channel_id)
