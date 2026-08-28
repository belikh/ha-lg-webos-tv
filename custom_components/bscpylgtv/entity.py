"""Base entity for the LG WebOS TV (bscpylgtv) integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, Concatenate, cast

from homeassistant.const import CONF_MAC
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from bscpylgtv import WebOsClient

from .const import BSCP_EXCEPTIONS, COMMAND_TIMEOUT, DOMAIN, LOGGER
from .coordinator import BscpylgtvConfigEntry, BscpylgtvCoordinator

# Commands that must bypass the device-off guard: WOL turn_on works while
# the TV is off, and turn_off on an off TV is a harmless no-op server-side.
_OFF_GUARD_EXEMPT = frozenset({"async_turn_on", "async_turn_off"})


class BscpylgtvEntity(CoordinatorEntity[BscpylgtvCoordinator]):
    """Base entity for one LG webOS TV."""

    _attr_has_entity_name = True
    _attr_device_info: DeviceInfo

    def __init__(self, entry: BscpylgtvConfigEntry) -> None:
        """Initialize the entity."""
        super().__init__(entry.runtime_data)
        self._entry = entry
        connections = set()
        if (mac := entry.data.get(CONF_MAC)) is not None:
            connections.add((dr.CONNECTION_NETWORK_MAC, mac))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, cast(str, entry.unique_id))},
            connections=connections,
            manufacturer="LG",
            name=entry.title,
        )
        self._device_info_signature: tuple[str | None, ...] | None = None

    @property
    def client(self) -> WebOsClient:
        """Return the current TV client.

        NEVER cache: the coordinator swaps the client object on every
        reconnect (zombie recovery replaces, not mutates, the client).
        """
        return self.coordinator.client

    @callback
    def _handle_coordinator_update(self) -> None:
        """Enrich the device entry as TV data arrives, then write state."""
        self._update_device_info()
        super()._handle_coordinator_update()

    @callback
    def _update_device_info(self) -> None:
        """Enrich the device registry entry with model/firmware once known.

        The TV may be off at setup time, so the static ``_attr_device_info``
        carries identifiers only; the registry entry is merged here when the
        first live data arrives and whenever the reported values change.
        """
        system_info = self.client.system_info or {}
        software_info = self.client.software_info or {}
        model = system_info.get("modelName")
        sw_version = (
            ".".join(
                str(part)
                for part in (
                    software_info.get("major_ver"),
                    software_info.get("minor_ver"),
                )
                if part is not None
            )
            or None
        )
        signature = (model, sw_version)
        if signature == self._device_info_signature:
            return
        self._device_info_signature = signature
        device_registry = dr.async_get(self.hass)
        device_registry.async_get_or_create(
            config_entry_id=self._entry.entry_id,
            identifiers={(DOMAIN, cast(str, self._entry.unique_id))},
            manufacturer="LG",
            name=self._entry.title,
            model=model,
            sw_version=sw_version,
        )


def cmd[EntityT: BscpylgtvEntity, R, **P](
    func: Callable[Concatenate[EntityT, P], Coroutine[Any, Any, R]],
) -> Callable[Concatenate[EntityT, P], Coroutine[Any, Any, R]]:
    """Wrap a TV command: bound it, retry once after a reconnect, translate.

    - Every attempt is bounded by COMMAND_TIMEOUT: a request on a zombie
      socket would otherwise hang forever.
    - On failure, one locked reconnect+retry runs against the fresh client
      (the client is re-resolved through the entity property, never cached).
    - A persistent failure raises a translated ``HomeAssistantError``
      (``communication_error``); commands against an off TV raise
      ``device_off`` up front instead.
    """

    @wraps(func)
    async def cmd_wrapper(self: EntityT, *args: P.args, **kwargs: P.kwargs) -> R:
        """Wrap all command methods."""
        if not self.client.is_on and func.__name__ not in _OFF_GUARD_EXEMPT:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="device_off",
                translation_placeholders={
                    "name": self.coordinator.name,
                    "func": func.__name__,
                },
            )
        try:
            return await asyncio.wait_for(func(self, *args, **kwargs), COMMAND_TIMEOUT)
        except BSCP_EXCEPTIONS as ex:
            LOGGER.debug(
                "Command %s failed (%s); reconnecting and retrying",
                func.__name__,
                ex,
            )
        await self.coordinator.async_recover()
        try:
            return await asyncio.wait_for(func(self, *args, **kwargs), COMMAND_TIMEOUT)
        except BSCP_EXCEPTIONS as ex:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={
                    "name": self.coordinator.name,
                    "func": func.__name__,
                    "error": str(ex),
                },
            ) from ex

    return cmd_wrapper
