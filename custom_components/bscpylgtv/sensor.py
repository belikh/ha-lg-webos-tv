"""Sensor entities for the LG WebOS TV (bscpylgtv) integration.

Four sensors (plan AD-15): ``current_app`` (title-resolved via the apps
dict), ``volume`` (percent, MEASUREMENT), ``power_state`` (ENUM with the
fixed webOS power-state options) and ``current_channel`` (DIAGNOSTIC,
``"<channelNumber> <channelName>"``). Model/firmware/UUID deliberately
live in the device registry entry, not sensors. All sensors are
``CoordinatorEntity``-driven: the push coordinator fires
``_handle_coordinator_update`` (inherited: writes state) whenever the
TV pushes or the watchdog ticks; ``should_poll`` is inherited False.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from bscpylgtv import WebOsClient

from .coordinator import BscpylgtvConfigEntry
from .entity import BscpylgtvEntity
from .select import format_channel

PARALLEL_UPDATES = 0

# Fixed option set for the ENUM power_state sensor (plan AD-15). Values
# are the webOS power states the library reports (get_power_state);
# anything unexpected is folded onto "Unknown" so the ENUM contract
# (native_value ∈ options) always holds.
POWER_STATE_OPTIONS: tuple[str, ...] = (
    "Active",
    "Active Standby",
    "Screen Off",
    "Suspend",
    "Request Active",
    "Power Off",
    "Unknown",
)


def _current_app_value(client: WebOsClient) -> StateType:
    """Resolve the foreground app id to its title (fallback: raw id)."""
    app_id = client.current_appId
    if not app_id:
        return None
    app = (client.apps or {}).get(app_id)
    if isinstance(app, dict) and app.get("title"):
        return str(app["title"])
    return str(app_id)


def _volume_value(client: WebOsClient) -> StateType:
    """Return the subscribed volume (None until the TV pushes one)."""
    return client.volume


def _power_state_value(client: WebOsClient) -> StateType:
    """Return the current power state, folded onto the option set."""
    state = (client.power_state or {}).get("state", "Unknown")
    return state if state in POWER_STATE_OPTIONS else "Unknown"


def _current_channel_value(client: WebOsClient) -> StateType:
    """Return the current channel formatted like the channel select."""
    channel = client.current_channel
    return format_channel(channel) if channel else None


@dataclass(frozen=True, kw_only=True)
class BscpylgtvSensorEntityDescription(SensorEntityDescription):
    """Describes a bscpylgtv sensor with its client-derived value."""

    value_fn: Callable[[WebOsClient], StateType]


SENSORS: tuple[BscpylgtvSensorEntityDescription, ...] = (
    BscpylgtvSensorEntityDescription(
        key="current_app",
        translation_key="current_app",
        value_fn=_current_app_value,
    ),
    BscpylgtvSensorEntityDescription(
        key="volume",
        translation_key="volume",
        # SensorDeviceClass.PERCENTAGE no longer exists in Home Assistant
        # (removed upstream); the "%" unit plus MEASUREMENT state class
        # carry the same semantics.
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_volume_value,
    ),
    BscpylgtvSensorEntityDescription(
        key="power_state",
        translation_key="power_state",
        device_class=SensorDeviceClass.ENUM,
        options=list(POWER_STATE_OPTIONS),
        value_fn=_power_state_value,
    ),
    BscpylgtvSensorEntityDescription(
        key="current_channel",
        translation_key="current_channel",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_current_channel_value,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BscpylgtvConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the LG WebOS TV sensor platform."""
    async_add_entities(BscpylgtvSensor(entry, description) for description in SENSORS)


class BscpylgtvSensor(BscpylgtvEntity, SensorEntity):
    """A sensor reading live client state (push/coordinator driven)."""

    entity_description: BscpylgtvSensorEntityDescription

    def __init__(
        self,
        entry: BscpylgtvConfigEntry,
        description: BscpylgtvSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"

    @property
    @override
    def native_value(self) -> StateType:
        """Return the sensor value derived from the live client state."""
        return self.entity_description.value_fn(self.client)
