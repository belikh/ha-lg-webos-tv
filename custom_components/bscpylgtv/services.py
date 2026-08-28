"""Entity services for the LG WebOS TV (bscpylgtv) integration.

All six services (plan AD-14) target this integration's media player
entities and are registered once from the integration's ``async_setup``
(quality-scale ``action-setup``) — never per config entry. All
human-readable strings live in ``translations/en.json``; services.yaml
carries structure only (AC-24).
"""

import voluptuous as vol
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.core import HomeAssistant, SupportsResponse, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service
from homeassistant.helpers.typing import VolDictType

from .const import (
    ATTR_BUTTON,
    ATTR_COMMAND,
    ATTR_PAYLOAD,
    ATTR_SOUND_OUTPUT,
    DOMAIN,
)

SERVICE_BUTTON = "button"
SERVICE_COMMAND = "command"
SERVICE_SELECT_SOUND_OUTPUT = "select_sound_output"
SERVICE_LAUNCH_APP = "launch_app"
SERVICE_TAKE_SCREENSHOT = "take_screenshot"
SERVICE_SET_SETTINGS = "set_settings"

BUTTON_SCHEMA: VolDictType = {vol.Required(ATTR_BUTTON): cv.string}
COMMAND_SCHEMA: VolDictType = {
    vol.Required(ATTR_COMMAND): cv.string,
    vol.Optional(ATTR_PAYLOAD): dict,
}
SOUND_OUTPUT_SCHEMA: VolDictType = {vol.Required(ATTR_SOUND_OUTPUT): cv.string}
LAUNCH_APP_SCHEMA: VolDictType = {
    vol.Required("app_id"): cv.string,
    vol.Optional("params"): dict,
}
TAKE_SCREENSHOT_SCHEMA: VolDictType = {vol.Optional("filename"): cv.string}
SET_SETTINGS_SCHEMA: VolDictType = {
    vol.Required("category"): cv.string,
    vol.Required("settings"): dict,
}

# (service, schema, media-player entity method, response mode)
SERVICES: tuple[tuple[str, VolDictType, str, SupportsResponse], ...] = (
    (SERVICE_BUTTON, BUTTON_SCHEMA, "async_button", SupportsResponse.NONE),
    (SERVICE_COMMAND, COMMAND_SCHEMA, "async_command", SupportsResponse.OPTIONAL),
    (
        SERVICE_SELECT_SOUND_OUTPUT,
        SOUND_OUTPUT_SCHEMA,
        "async_select_sound_output",
        SupportsResponse.OPTIONAL,
    ),
    (SERVICE_LAUNCH_APP, LAUNCH_APP_SCHEMA, "async_launch_app", SupportsResponse.NONE),
    (
        SERVICE_TAKE_SCREENSHOT,
        TAKE_SCREENSHOT_SCHEMA,
        "async_take_screenshot",
        SupportsResponse.OPTIONAL,
    ),
    (
        SERVICE_SET_SETTINGS,
        SET_SETTINGS_SCHEMA,
        "async_set_settings",
        SupportsResponse.NONE,
    ),
)


@callback
def async_setup(hass: HomeAssistant) -> None:
    """Register all bscpylgtv entity services (called once at setup)."""
    for service_name, schema, func, supports_response in SERVICES:
        service.async_register_platform_entity_service(
            hass,
            DOMAIN,
            service_name,
            entity_domain=MEDIA_PLAYER_DOMAIN,
            func=func,
            schema=schema,
            supports_response=supports_response,
        )
