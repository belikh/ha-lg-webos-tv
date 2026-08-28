"""Number entities for the LG WebOS TV (bscpylgtv) integration.

Six picture-setting sliders (plan AD-12): backlight, contrast,
brightness, color, sharpness and colorTemperature. Ranges come from
``PICTURE_NUMBER_RANGES`` (Cluster A, verified against the C2 ground
truth); the phantom v1 ``oled_light`` number is gone — OLED light IS
``backlight``. All entities are CONFIG category and disabled by default.

Value sources differ by key (webos_client.subscribe_picture_settings
only pushes ``contrast``/``backlight``/``brightness``/``color``):

* pushed keys read from the subscribed ``picture_settings`` state;
* ``sharpness``/``colorTemperature`` are read once per (re)connect via a
  guarded one-shot ``get_picture_settings`` call and optimistically
  mirrored after each write (Luna writes are one-way: the library cannot
  read back what ``set_settings`` changed).

Writes always go through ``set_settings("picture", {key: int(value)})``
(the Luna path — the public SSAP ``set_system_settings`` rejects
picture-category writes on at least some models).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from bscpylgtv import WebOsClient

from .const import BSCP_EXCEPTIONS, COMMAND_TIMEOUT, LOGGER, PICTURE_NUMBER_RANGES
from .coordinator import BscpylgtvConfigEntry
from .entity import BscpylgtvEntity, cmd

PARALLEL_UPDATES = 0

# Keys pushed by the library's default picture-settings subscription
# (webos_client.subscribe_picture_settings defaults); every other key
# needs the one-shot read below (plan AD-12).
_PUSHED_PICTURE_KEYS = frozenset({"backlight", "contrast", "brightness", "color"})


@dataclass(frozen=True, kw_only=True)
class PictureNumberSpec:
    """One slider: webOS settings key + translation/unique-id key."""

    key: str
    translation_key: str
    needs_read: bool


# webOS settings key + translation_key (== unique_id suffix) per plan §3.2;
# only ``colorTemperature`` differs (suffix/translation "color_temperature").
PICTURE_NUMBERS: tuple[PictureNumberSpec, ...] = tuple(
    PictureNumberSpec(
        key=key,
        translation_key=translation_key,
        needs_read=key not in _PUSHED_PICTURE_KEYS,
    )
    for key, translation_key in (
        ("backlight", "backlight"),
        ("contrast", "contrast"),
        ("brightness", "brightness"),
        ("color", "color"),
        ("sharpness", "sharpness"),
        ("colorTemperature", "color_temperature"),
    )
)


def _int_or_none(value: Any) -> int | None:
    """Coerce a (possibly string) settings value to int; None if not.

    webOS settings responses carry the values as strings ("sharpness":
    "10" in the C2 dump), so a plain isinstance check is not enough.
    """
    if value is None:
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BscpylgtvConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the LG WebOS TV number platform."""
    async_add_entities(BscpylgtvPictureNumber(entry, spec) for spec in PICTURE_NUMBERS)


class BscpylgtvPictureNumber(BscpylgtvEntity, NumberEntity):
    """A webOS picture-setting slider (plan AD-12)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 1

    def __init__(self, entry: BscpylgtvConfigEntry, spec: PictureNumberSpec) -> None:
        """Initialize the slider from its spec and the frozen C2 range."""
        super().__init__(entry)
        self._spec = spec
        self._attr_translation_key = spec.translation_key
        self._attr_unique_id = f"{entry.unique_id}_{spec.translation_key}"
        native_min, native_max = PICTURE_NUMBER_RANGES[spec.key]
        self._attr_native_min_value = float(native_min)
        self._attr_native_max_value = float(native_max)
        # Client instance the one-shot read has already run for (None
        # until then); doubles as the "value read once per (re)connect"
        # guard because the coordinator swaps the client object on every
        # reconnect (AD-4).
        self._read_client: WebOsClient | None = None
        # Last push seen for this key (staleness marker, see below).
        self._pushed_value: int | None = None
        # Last value from a fresh push, the one-shot read, or an
        # optimistic write-back.
        self._local_value: int | None = None

    @property
    @override
    def native_value(self) -> float | None:
        """Return the current setting.

        The tracked value (``_local_value``) is authoritative; before
        the first coordinator update it falls back to whatever the
        subscribed ``picture_settings`` state already carries.
        """
        if self._local_value is not None:
            return float(self._local_value)
        pushed = _int_or_none((self.client.picture_settings or {}).get(self._spec.key))
        return float(pushed) if pushed is not None else None

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Reconcile pushes, schedule one-shot reads, then write state."""
        pushed = _int_or_none((self.client.picture_settings or {}).get(self._spec.key))
        if pushed is not None and pushed != self._pushed_value:
            # A *changed* push is authoritative and overrides the
            # optimistic write-back below. An unchanged push is a stale
            # echo of the value that was live before our Luna write (the
            # TV does not reliably echo settings changed through Luna),
            # so it must not clobber the optimistic value.
            self._pushed_value = pushed
            self._local_value = pushed
        if self._spec.needs_read:
            self._async_schedule_oneshot_read()
        super()._handle_coordinator_update()

    @callback
    def _async_schedule_oneshot_read(self) -> None:
        """Ensure one value read per (re)connected client (plan AD-12).

        The client-identity check scopes the read to once per (re)connect
        (the coordinator replaces the client object on every reconnect).
        While the TV is off the client is disconnected, so the guard
        simply waits; a failed read gives up until the next reconnect
        instead of retrying every watchdog tick.
        """
        client = self.client
        if self._read_client is client or not client.is_connected():
            return
        self._read_client = client
        self.hass.async_create_task(self._async_oneshot_read())

    async def _async_oneshot_read(self) -> None:
        """Read the value once; best-effort, never surfaces an error."""
        if not self.client.is_on:
            # TV went away again; allow a retry on a later update.
            self._read_client = None
            return
        try:
            settings = await asyncio.wait_for(
                self.client.get_picture_settings([self._spec.key]),
                COMMAND_TIMEOUT,
            )
        except BSCP_EXCEPTIONS as ex:
            # Read rejection varies by model/firmware (plan R-3/R-9);
            # keep the last-known value until the next reconnect.
            LOGGER.debug(
                "One-shot read of picture setting %s failed: %s",
                self._spec.key,
                ex,
            )
            return
        if (value := _int_or_none(settings.get(self._spec.key))) is not None:
            self._local_value = value
            self.async_write_ha_state()

    @cmd
    @override
    async def async_set_native_value(self, value: float) -> None:
        """Set the picture setting through the Luna path."""
        int_value = int(value)
        await self.client.set_settings("picture", {self._spec.key: int_value})
        # Luna writes are one-way (no readable confirmation), so mirror
        # the value optimistically until a push/read proves otherwise.
        self._local_value = int_value
        self.async_write_ha_state()
