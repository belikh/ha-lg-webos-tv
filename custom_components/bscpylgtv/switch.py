"""Switch entities for the LG WebOS TV (bscpylgtv) integration.

Two CONFIG-category, disabled-by-default switches (plan AC-23):
``tpc`` (Temporal Peak Control) and ``gsr`` (Global Stress Reduction) —
OLED panel-protection features toggled through the library's Luna
``enable_tpc_or_gsr`` writer.
"""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BscpylgtvConfigEntry
from .entity import BscpylgtvEntity, cmd

PARALLEL_UPDATES = 0

# (library algo name, translation_key == unique_id suffix) per plan §3.2.
_PROTECTIVE_FEATURES: tuple[tuple[str, str], ...] = (
    ("tpc", "tpc"),
    ("gsr", "gsr"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BscpylgtvConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the LG WebOS TV switch platform."""
    async_add_entities(
        BscpylgtvProtectiveFeatureSwitch(entry, algo, translation_key)
        for algo, translation_key in _PROTECTIVE_FEATURES
    )


class BscpylgtvProtectiveFeatureSwitch(BscpylgtvEntity, SwitchEntity):
    """A TPC/GSR OLED-protection toggle (Luna write, best-effort state).

    Honest read strategy (plan §8.4 item 4): webOS exposes NO readable
    settings key for these In-Start service-menu flags — they are absent
    from the available-settings dumps, and the Luna transport itself is
    one-way (webos_client.luna_request discards response data). The
    switch therefore reports ``None`` (unknown) until the first
    successful write in this HA session, then mirrors what was written.
    Home Assistant renders the unknown state as "off"-looking but
    unavailable-for-automation; after a restart it returns to unknown
    even though the TV kept the setting — a documented best-effort.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(
        self, entry: BscpylgtvConfigEntry, algo: str, translation_key: str
    ) -> None:
        """Initialize the switch for one protective feature."""
        super().__init__(entry)
        self._algo = algo
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{entry.unique_id}_{translation_key}"
        self._state: bool | None = None

    @property
    @override
    def is_on(self) -> bool | None:
        """Return the last successfully written value (None = unknown)."""
        return self._state

    @cmd
    async def _async_set(self, value: bool) -> None:
        """Toggle the feature through the Luna service-menu writer."""
        await self.client.enable_tpc_or_gsr(self._algo, value)

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the protective feature."""
        await self._async_set(True)
        self._state = True
        self.async_write_ha_state()

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the protective feature."""
        await self._async_set(False)
        self._state = False
        self.async_write_ha_state()
