"""Config flow for LG WebOS TV (bscpylgtv) integration."""
from __future__ import annotations

import logging
import os
import asyncio
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.components import ssdp

from bscpylgtv import WebOsClient
from .const import DOMAIN, CONF_KEY_FILE

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_IP_ADDRESS): str,
        vol.Optional(CONF_NAME, default="LG WebOS TV"): str,
    }
)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for LG WebOS TV."""

    VERSION = 1

    def __init__(self):
        """Initialize."""
        self._host: str | None = None
        self._name: str | None = None
        self._client: WebOsClient | None = None
        self._key_file_path: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = user_input[CONF_IP_ADDRESS]
            self._name = user_input.get(CONF_NAME, "LG WebOS TV")

            await self.async_set_unique_id(self._host)
            self._abort_if_unique_id_configured()

            # Prepare key file path
            # We use a file in .storage for this host
            filename = f"bscpylgtv_{self._host.replace('.', '_')}.sqlite"
            self._key_file_path = self.hass.config.path(".storage", filename)

            return await self.async_step_pairing()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_pairing(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the pairing step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Ensure directory exists (should exist but good practice)
                os.makedirs(os.path.dirname(self._key_file_path), exist_ok=True)

                self._client = await WebOsClient.create(
                    self._host,
                    key_file_path=self._key_file_path,
                    ping_interval=None,
                    states=[]
                )

                # Connect. This might block waiting for user input on TV.
                # We set a timeout for the user to accept.
                try:
                    await asyncio.wait_for(self._client.connect(), timeout=60)
                except asyncio.TimeoutError:
                    errors["base"] = "pairing_timeout"
                    if self._client:
                        await self._client.disconnect()
                    return self.async_show_form(step_id="pairing", errors=errors)

                if self._client.is_registered():
                    await self._client.disconnect()
                    return self.async_create_entry(
                        title=self._name,
                        data={
                            CONF_IP_ADDRESS: self._host,
                            CONF_KEY_FILE: self._key_file_path
                        },
                    )
                else:
                    errors["base"] = "pairing_failed"
                    await self._client.disconnect()

            except Exception:
                _LOGGER.exception("Unexpected exception during pairing")
                errors["base"] = "cannot_connect"
                if self._client:
                    await self._client.disconnect()

        return self.async_show_form(
            step_id="pairing",
            description_placeholders={"name": self._name},
            data_schema=vol.Schema({}),
            errors=errors
        )

    async def async_step_ssdp(self, discovery_info: ssdp.SsdpServiceInfo) -> FlowResult:
        """Handle SSDP discovery."""
        host = discovery_info.ssdp_location
        if host:
             parsed = urlparse(host)
             self._host = parsed.hostname
        else:
            self._host = discovery_info.ssdp_headers.get("_host")

        if not self._host:
            return self.async_abort(reason="no_host")

        self._name = discovery_info.upnp.get(ssdp.ATTR_UPNP_FRIENDLY_NAME, "LG WebOS TV")

        await self.async_set_unique_id(self._host)
        self._abort_if_unique_id_configured()

        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_user({CONF_IP_ADDRESS: self._host, CONF_NAME: self._name})
