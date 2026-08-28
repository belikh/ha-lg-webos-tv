"""The LG WebOS TV (bscpylgtv) integration."""

from __future__ import annotations

import asyncio
import importlib
import re
from contextlib import suppress
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_MAC, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from bscpylgtv import WebOsClient
from bscpylgtv.exceptions import PyLGTVPairException

from .const import (
    BSCP_CONNECTION_EXCEPTIONS,
    CONF_CLIENT_KEY,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DISCONNECT_TIMEOUT,
    DOMAIN,
    LOGGER,
    PLATFORMS,
    RECONNECT_TIMEOUT,
)
from .coordinator import (
    BscpylgtvConfigEntry,
    BscpylgtvCoordinator,
    make_runtime_client,
    release_client,
    update_client_key,
    update_mac_address,
)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# hass.data flag guarding one-time service registration (quality-scale
# ``action-setup``; services are registered in async_setup, not per entry).
_SERVICES_SETUP_FLAG = f"{DOMAIN}_services_setup"

# v1 config entries keyed their data by these literals. v1 unique_ids and
# entity ids were based on the raw IP; v2 keys everything on the deviceUUID.
_LEGACY_KEY_FILE = "key_file"
_LEGACY_IP_ADDRESS = "ip_address"

_IPV4_UNIQUE_ID_PATTERN = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the LG WebOS TV (bscpylgtv) integration."""
    if not hass.data.get(_SERVICES_SETUP_FLAG):
        hass.data[_SERVICES_SETUP_FLAG] = True
        # Entity services live in services.py (Cluster C). Imported at call
        # time via importlib so the package stays importable (and type-clean)
        # at every cluster boundary; the ImportError is swallowed until that
        # module lands. Keep as importlib: works unchanged once it exists.
        try:
            services = importlib.import_module(".services", __package__)
            services.async_setup(hass)
        except ImportError:
            LOGGER.debug("services module not available yet; skipping registration")
    return True


def _needs_unique_id_fix(unique_id: str | None) -> bool:
    """Return True for v1 unique_ids that are IP/hostname shaped."""
    if not unique_id:
        return False
    return bool(
        _IPV4_UNIQUE_ID_PATTERN.fullmatch(unique_id)
        or ":" in unique_id
        or "." in unique_id
    )


@callback
def _async_update_unique_id(
    hass: HomeAssistant, entry: BscpylgtvConfigEntry, client: WebOsClient
) -> None:
    """Lazily migrate a v1 IP-based unique_id to the device UUID (plan §7).

    Not migratable offline: it requires a live hello payload. Runs before
    platforms are forwarded so entities and the device registry bind to the
    UUID from the start of v2 life. Guarded against duplicates (R-11).
    """
    device_uuid = (client.hello_info or {}).get("deviceUUID")
    if not device_uuid or not _needs_unique_id_fix(entry.unique_id):
        return
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id != entry.entry_id and other.unique_id == device_uuid:
            LOGGER.warning(
                "Cannot update unique_id for %s: another entry already uses"
                " %s; remove the duplicate entry to resolve this",
                entry.title,
                device_uuid,
            )
            return
    try:
        hass.config_entries.async_update_entry(entry, unique_id=device_uuid)
    except HomeAssistantError, ValueError:
        LOGGER.warning(
            "Failed to update unique_id for %s; keeping existing value",
            entry.title,
        )


def _read_legacy_client_key(path: Path, host: str) -> str | None:
    """Read the v1 sqlite key file (sqlitedict, default table, IP keys)."""
    if not path.is_file():
        return None
    from sqlitedict import SqliteDict  # bscpylgtv dependency

    with SqliteDict(str(path)) as db:
        return db.get(host)  # type: ignore[no-any-return]


async def _async_read_legacy_client_key(
    hass: HomeAssistant, key_file: str, host: str
) -> str | None:
    """Read the legacy pairing key in the executor; silent fallback (§7).

    Any failure (missing/corrupt file, lock) degrades to a keyless entry;
    the first setup then raises ConfigEntryAuthFailed and the reauth flow
    re-pairs with the user. No user-facing error during migration itself.
    """
    path = Path(key_file)
    if not path.is_absolute():
        # v1 stored paths relative to the config directory.
        path = Path(hass.config.config_dir) / path
    try:
        return await hass.async_add_executor_job(_read_legacy_client_key, path, host)
    except Exception:  # noqa: BLE001 - silent fallback is mandated (plan §7)
        LOGGER.debug("Could not read legacy key file %s", path, exc_info=True)
        return None


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries to the current schema (plan §7)."""
    if entry.version == 1:
        old_data = dict(entry.data)
        host = old_data.get(_LEGACY_IP_ADDRESS)
        if not host:
            LOGGER.error("Cannot migrate entry %s: no host found", entry.title)
            return False
        new_data: dict[str, Any] = {CONF_HOST: host}
        if (mac := old_data.get(CONF_MAC)) is not None:
            new_data[CONF_MAC] = mac
        # "name" and "key_file" are dropped on purpose (title keeps the name).
        if key_file := old_data.get(_LEGACY_KEY_FILE):
            client_key = await _async_read_legacy_client_key(hass, key_file, host)
            if client_key is not None:
                new_data[CONF_CLIENT_KEY] = client_key
        # The legacy sqlite file is intentionally NOT deleted (user cleanup).
        hass.config_entries.async_update_entry(
            entry,
            data=new_data,
            version=CONFIG_ENTRY_VERSION,
            minor_version=CONFIG_ENTRY_MINOR_VERSION,
        )
        LOGGER.debug("Migrated config entry %s to v2", entry.title)
        return True
    if (
        entry.version == CONFIG_ENTRY_VERSION
        and entry.minor_version < CONFIG_ENTRY_MINOR_VERSION
    ):
        hass.config_entries.async_update_entry(
            entry, minor_version=CONFIG_ENTRY_MINOR_VERSION
        )
    return True


async def _async_teardown_client(hass: HomeAssistant, client: WebOsClient) -> None:
    """Disconnect a healthy client; abandon a suspect one (never hang).

    The healthy stop path uses a bounded disconnect; if it does not finish
    within DISCONNECT_TIMEOUT the client is treated as a zombie and
    released instead (the library's teardown shield-loop can block forever
    on a dead socket — R-6).
    """
    client.clear_state_update_callbacks()
    try:
        await asyncio.wait_for(client.disconnect(), DISCONNECT_TIMEOUT)
    except Exception:  # noqa: BLE001 - abandon, never block unload/stop
        LOGGER.debug("Disconnect did not finish in time; abandoning client")
        release_client(client)


async def async_setup_entry(hass: HomeAssistant, entry: BscpylgtvConfigEntry) -> bool:
    """Set up a config entry for an LG WebOS TV."""
    if not entry.data.get(CONF_CLIENT_KEY):
        # Keyless entries (unreadable legacy sqlite migration, §7) cannot
        # pair in the background — PROMPT pairing would spam the TV on every
        # watchdog tick. Fail to the reauth flow, which re-pairs explicitly.
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key="auth_failed",
            translation_placeholders={"device": entry.title},
        )

    client = await make_runtime_client(
        hass, entry.data[CONF_HOST], entry.data.get(CONF_CLIENT_KEY)
    )
    coordinator = BscpylgtvCoordinator(hass, entry, client)
    entry.runtime_data = coordinator

    # Register the push callback BEFORE connect: connect fires callbacks at
    # the end of a successful handshake, and the library clears the callback
    # list on teardown, so every fresh client must re-register (AD-2).
    # state_update_task (not async_handle_update): the library's teardown
    # closeout feeds callback results to asyncio.wait, which rejects raw
    # coroutines on Python 3.11+ and would kill disconnect()/unload.
    await client.register_state_update_callback(coordinator.state_update_task)

    # No async_config_entry_first_refresh here (AC-15): this is a push
    # coordinator — the library callback populates state and the 10 s
    # interval only supervises the connection. A first refresh would fail
    # the entry when the TV is off, which this integration tolerates.
    with suppress(*BSCP_CONNECTION_EXCEPTIONS):
        try:
            await asyncio.wait_for(client.connect(), timeout=RECONNECT_TIMEOUT)
        except PyLGTVPairException as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="auth_failed",
                translation_placeholders={"device": entry.title},
            ) from err

    if client.is_connected():
        # Lazy v1 -> v2 unique_id fix needs a live hello (deviceUUID).
        _async_update_unique_id(hass, entry, client)
        update_client_key(hass, entry, client)
        update_mac_address(hass, entry, client)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def async_on_stop(_event: Event) -> None:
        """Tear down the client when Home Assistant stops (bounded)."""
        await _async_teardown_client(hass, coordinator.client)

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_on_stop)
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BscpylgtvConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await _async_teardown_client(hass, entry.runtime_data.client)
    return unload_ok
