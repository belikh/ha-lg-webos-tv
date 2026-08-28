"""Notification entity for the LG WebOS TV (bscpylgtv) integration.

Plan AC-23: sends on-TV toasts. The toast payload is built here and
sent through the raw SSAP ``system.notifications/createToast`` endpoint
because the library's ``send_message(message, icon_path)`` reads the
icon file with a blocking ``open()`` on the event loop; the icon is
read in an executor instead, and the wire payload matches the
library's exactly (``message`` / ``iconData`` / ``iconExtension``).
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Any, override

from homeassistant.components.notify import (
    ATTR_DATA,
    NotifyEntity,
    NotifyEntityFeature,
)
from homeassistant.const import ATTR_ICON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from bscpylgtv.endpoints import SHOW_MESSAGE

from .const import BSCP_EXCEPTIONS, COMMAND_TIMEOUT, DOMAIN
from .coordinator import BscpylgtvConfigEntry
from .entity import BscpylgtvEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BscpylgtvConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the notification platform."""
    async_add_entities([BscpylgtvNotifyEntity(entry)])


def _read_icon(icon_path: str) -> tuple[str, str]:
    """Read and base64-encode an icon file (executor only; blocking I/O)."""
    path = Path(icon_path)
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return encoded, path.suffix[1:]


class BscpylgtvNotifyEntity(BscpylgtvEntity, NotifyEntity):
    """Notify entity that shows a toast on the TV."""

    _attr_translation_key = "notify"
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, entry: BscpylgtvConfigEntry) -> None:
        """Initialize the notification entity."""
        super().__init__(entry)
        self._attr_unique_id = f"{entry.unique_id}_notify"

    @override
    async def async_send_message(
        self, message: str, title: str | None = None, **kwargs: Any
    ) -> None:
        """Send a toast message to the TV.

        ``title`` is prefixed to the message (``"<title>: <message>"``):
        a webOS toast is a single line of text with no separate title
        element (documented choice).

        ``data.icon`` (a local file path) is read in the executor and
        attached to the toast. Note: in HA 2026.8 the notify entity
        service schema carries only ``message`` and ``title`` — the
        ``data`` mapping never reaches notify entities — so the icon
        path is only reachable from direct entity calls today; the
        implementation is kept per AC-23 so it works as soon as HA
        forwards ``data`` again.
        """
        if title:
            message = f"{title}: {message}"
        client = self.client
        if not client.is_on:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="notify_device_off",
                translation_placeholders={"name": self._entry.title},
            )

        icon_data = ""
        icon_extension = ""
        data = kwargs.get(ATTR_DATA) or {}
        if icon_path := data.get(ATTR_ICON):
            try:
                icon_data, icon_extension = await self.hass.async_add_executor_job(
                    _read_icon, str(icon_path)
                )
            except OSError as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="notify_icon_not_found",
                    translation_placeholders={
                        "name": self._entry.title,
                        "icon_path": str(icon_path),
                    },
                ) from err

        payload = {
            "message": message,
            "iconData": icon_data,
            "iconExtension": icon_extension,
        }
        try:
            await asyncio.wait_for(
                client.request(SHOW_MESSAGE, payload), COMMAND_TIMEOUT
            )
        except BSCP_EXCEPTIONS as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="notify_communication_error",
                translation_placeholders={
                    "name": self._entry.title,
                    "error": str(err),
                },
            ) from err
