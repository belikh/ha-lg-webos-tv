"""Constants for the LG WebOS TV (bscpylgtv) integration.

This module is owned by Cluster A and is the single shared constants
surface: every other module imports from here only (plan §4 ownership
rule). ``CONF_HOST``/``CONF_MAC`` are re-exported from
``homeassistant.const`` so downstream modules never import them directly.
"""

import logging
from datetime import timedelta

from homeassistant.const import CONF_HOST, CONF_MAC, Platform  # noqa: F401 - re-export

from bscpylgtv.buttons import BUTTONS  # noqa: F401 - re-exported for validation
from bscpylgtv.exceptions import (
    PyLGTVCmdError,
    PyLGTVCmdException,
    PyLGTVPairException,
    PyLGTVServiceNotFoundError,
)

DOMAIN = "bscpylgtv"
LOGGER = logging.getLogger(__package__)

# Config-entry schema versions (config_flow.VERSION / async_migrate_entry).
CONFIG_ENTRY_VERSION = 2
CONFIG_ENTRY_MINOR_VERSION = 1

PLATFORMS: list[Platform] = [
    Platform.MEDIA_PLAYER,
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.REMOTE,
    Platform.NOTIFY,
]

DEFAULT_NAME = "LG WebOS TV"

# Config-entry data keys. CONF_HOST ("host") and CONF_MAC ("mac") come from
# homeassistant.const; the library pairing key is stored as "client_key"
# (NOT homeassistant's CONF_CLIENT_SECRET, to match the library field name).
CONF_CLIENT_KEY = "client_key"
CONF_SOURCES = "sources"

# Attributes shared across platforms/services.
ATTR_BUTTON = "button"
ATTR_COMMAND = "command"
ATTR_PAYLOAD = "payload"
ATTR_SOUND_OUTPUT = "sound_output"

LIVE_TV_APP_ID = "com.webos.app.livetv"

# Exactly the library's default subscription set (webos_client.py). Do NOT
# add channels/current_channel/channel_info: connect-time subscription
# failures are only tolerated for PyLGTVCmdError/PyLGTVServiceNotFoundError;
# the channels trio is auto-subscribed lazily and safely once Live TV is in
# the foreground (plan AD-2). Must stay a list: the library constructor does
# ``set(states) if isinstance(states, list) else set()``.
DEFAULT_STATES = [
    "system_info",
    "software_info",
    "power",
    "current_app",
    "muted",
    "volume",
    "apps",
    "inputs",
    "sound_output",
    "picture_settings",
]

# Timing constants (lgtv-ha connection.py + lg_oled_control guidance).
# SCAN_INTERVAL is a supervisory watchdog interval, not a poll: a healthy
# push connection is probed, never re-fetched.
SCAN_INTERVAL = timedelta(seconds=10)
PROBE_TIMEOUT = 5
COMMAND_TIMEOUT = 8
RECONNECT_TIMEOUT = 15
DISCONNECT_TIMEOUT = 2

# UDP port for in-integration wake-on-lan magic packets (AD-8).
WOL_PORT = 9

# websockets transport exceptions raised under the socket; guarded import
# because the integration must stay importable in any environment.
_WS_EXCEPTIONS: tuple[type[Exception], ...]
try:
    from websockets.exceptions import WebSocketException

    _WS_EXCEPTIONS = (WebSocketException,)
except ImportError:  # pragma: no cover - websockets ships with bscpylgtv
    _WS_EXCEPTIONS = ()

# Everything a TV command/connect can raise (plan AD-3 / research §8.4.9).
# TimeoutError subclasses OSError since Python 3.10, listed for clarity.
BSCP_EXCEPTIONS: tuple[type[Exception], ...] = (
    PyLGTVPairException,
    PyLGTVCmdException,
    PyLGTVCmdError,
    PyLGTVServiceNotFoundError,
    TimeoutError,
    OSError,
    *_WS_EXCEPTIONS,
)

# Connection-level subset (no pairing errors): used where a pairing failure
# must surface as ConfigEntryAuthFailed instead of being suppressed.
BSCP_CONNECTION_EXCEPTIONS: tuple[type[Exception], ...] = tuple(
    exc for exc in BSCP_EXCEPTIONS if exc is not PyLGTVPairException
)

# Curated fallback sound outputs (webOS C2 ``soundOutputList`` enum plus the
# apiadapter runtime names such as "external_speaker"). The sound-output
# select unions the TV's current value into this list (AD-13).
SOUND_OUTPUTS: tuple[str, ...] = (
    "tv_speaker",
    "external_optical",
    "external_arc",
    "external_speaker",
    "tv_external_speaker",
    "lineout",
    "headphone",
    "bt_soundbar",
    "lgSoundSync",
    "wisa_speaker",
    "usb_speaker",
)

# Curated fallback picture modes (AD-13): correct webOS names from the
# library's set_picture_mode docstring / C2 §3.5 union. Used only when the
# live ``get_system_settings("picture", ["pictureMode"])`` enum read fails.
PICTURE_MODES_FALLBACK: tuple[str, ...] = (
    "normal",
    "vivid",
    "cinema",
    "eco",
    "sports",
    "game",
    "photo",
    "expert1",
    "expert2",
    "filmMaker",
    "hdrCinema",
    "hdrCinemaBright",
    "hdrFilmMaker",
    "hdrGame",
    "hdrStandard",
    "hdrVivid",
    "dolbyHdrCinema",
    "dolbyHdrCinemaBright",
    "dolbyHdrDarkAmazon",
    "dolbyHdrGame",
    "dolbyHdrStandard",
    "dolbyHdrVivid",
)

# Number-entity ranges keyed by the webOS picture-settings key (AD-12,
# verified against available_settings_C2.md; OLED light IS "backlight").
PICTURE_NUMBER_RANGES: dict[str, tuple[int, int]] = {
    "backlight": (0, 100),
    "contrast": (0, 100),
    "brightness": (0, 100),
    "color": (0, 100),
    "sharpness": (0, 50),
    "colorTemperature": (-50, 50),
}

# HA-style remote key aliases mapped to bscpylgtv BUTTONS names (AD-16).
# All other library button names (bscpylgtv.buttons.BUTTONS, 77 entries)
# are accepted verbatim by the remote entity.
REMOTE_BUTTON_ALIASES: dict[str, str] = {
    "SELECT": "ENTER",
    "VOLUME_UP": "VOLUMEUP",
    "VOLUME_DOWN": "VOLUMEDOWN",
}

# Virtual pointer/IME commands handled specially by the remote entity.
REMOTE_SPECIAL_COMMANDS: frozenset[str] = frozenset({"CLICK", "MOVE", "SCROLL", "TEXT"})
