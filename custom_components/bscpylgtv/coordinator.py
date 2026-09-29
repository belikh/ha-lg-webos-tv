"""Coordinator for the LG WebOS TV (bscpylgtv) integration.

bscpylgtv pushes state over its websocket and invokes the registered
callback; the 10 s ``update_interval`` is a supervisory watchdog only —
it never polls a healthy connection. Each tick probes the link with a
real, timeout-bounded request (``is_connected()`` only reports connect
task liveness and can be fooled by a zombie socket) and, when the link
is dead, abandons the wedged client and connects a fresh one.

Teardown discipline (lgtv-ha connection.py): the library's teardown
re-shields its closeout task and swallows ``CancelledError`` until a
``ws.close()`` handshake a dead socket never completes, so
``await disconnect()`` on a suspect client is uncancellable. Such clients
are *abandoned* (best-effort ``connect_task.cancel()``, never awaited)
and replaced.
"""

from __future__ import annotations

import asyncio
import base64
import functools
import re
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from bscpylgtv import WebOsClient
from bscpylgtv.exceptions import PyLGTVPairException
from bscpylgtv.manifest import MANIFEST

from .const import (
    BSCP_CONNECTION_EXCEPTIONS,
    CONF_CLIENT_KEY,
    CONF_MAC,
    DEFAULT_STATES,
    DISCONNECT_TIMEOUT,
    DOMAIN,
    HELLO_PROBE_TIMEOUT,
    LOGGER,
    PROBE_TIMEOUT,
    RECONNECT_TIMEOUT,
    SCAN_INTERVAL,
)
from .key_storage import InMemoryKeyStorage


def build_unsigned_manifest() -> dict[str, Any]:
    """Return bscpylgtv's manifest without the blacklisted signature block.

    webOS 26 (firmware 43.x) rejects the legacy signed manifest with a
    ``403 Pairing rejected: blacklisted certificate detected`` registration
    error and invalidates existing pairing keys. The recovery, matching
    aiowebostv's fix for Home Assistant core (PR #719), is to drop
    ``signatures``/``signed`` and move the signed-only permissions into the
    outer permissions block that the on-screen pairing prompt grants.

    Derived from the pinned library's manifest at runtime so it cannot
    drift from the bscpylgtv version in use. Callers only fall back to it
    after the signed manifest was rejected: TVs that still accept the
    signed block keep its elevated permissions (WRITE_SETTINGS, used for
    picture settings, is signed-only on many sets).
    """
    manifest = {
        key: value
        for key, value in MANIFEST.items()
        if key not in ("signatures", "signed")
    }
    signed = MANIFEST.get("signed") or {}
    permissions = list(
        dict.fromkeys(
            [*manifest.get("permissions", []), *signed.get("permissions", [])]
        )
    )
    return {**manifest, "permissions": permissions}


async def make_runtime_client(
    hass: HomeAssistant,
    host: str,
    client_key: str | None,
    *,
    get_hello_info: bool = False,
    states: list[str] | None = None,
    unsigned_manifest: bool = False,
) -> WebOsClient:
    """Build a client with the AD-2 kwargs.

    The constructor builds an SSL context (blocking I/O), so it always
    runs in an executor. ``InMemoryKeyStorage`` is always injected: the
    library writes freshly paired keys through ``storage.set_key`` during
    registration and would raise ``AttributeError`` without it.

    ``get_hello_info`` defaults to False: on webOS 25 the hello message is
    never answered and blocks connect() until the caller's timeout
    (belikh/ha-lg-webos-tv#11). Only the bounded UUID probe asks for it.
    ``states`` must be a list — the library treats any other type as empty.
    ``unsigned_manifest`` swaps in the webOS 26-compatible registration
    manifest (see ``build_unsigned_manifest``); it defaults to False and is
    only used when a signed attempt was rejected.
    """
    client = await hass.async_add_executor_job(
        functools.partial(
            WebOsClient,
            host,
            client_key=client_key,
            storage=InMemoryKeyStorage(client_key),
            timeout_connect=10,
            connect_retry_attempts=1,
            ping_interval=10,
            volume_step_delay_ms=100,
            get_hello_info=get_hello_info,
            states=DEFAULT_STATES if states is None else states,
        )
    )
    if unsigned_manifest:
        client.manifest = build_unsigned_manifest()
    return client


async def make_pairing_client(
    hass: HomeAssistant, host: str, *, unsigned_manifest: bool = False
) -> WebOsClient:
    """Build a fresh-pairing client for the config flow (AD-2).

    Consumed read-only by the config flow (Cluster B): empty storage (the
    library stores the new key there and exposes it as ``client.client_key``),
    PROMPT pairing (never PIN — the PIN path does blocking ``input()``), no
    state subscriptions and NO hello: requesting hello hangs pairing on
    webOS 25 before registration is ever sent, so the TV never shows the
    prompt (belikh/ha-lg-webos-tv#11). The device UUID is recovered after
    pairing with the bounded, silent probe in ``async_probe_device_uuid``.
    ``unsigned_manifest`` is the webOS 26 retry (see
    ``build_unsigned_manifest``).
    """
    client = await hass.async_add_executor_job(
        functools.partial(
            WebOsClient,
            host,
            storage=InMemoryKeyStorage(None),
            pairing_type="PROMPT",
            timeout_connect=10,
            connect_retry_attempts=1,
            states=[],
            get_hello_info=False,
        )
    )
    if unsigned_manifest:
        client.manifest = build_unsigned_manifest()
    return client


async def async_probe_device_uuid(
    hass: HomeAssistant, host: str, client_key: str | None
) -> str | None:
    """Return the hello ``deviceUUID`` for a paired TV, or None.

    Runs a second, strongly bounded connection that is already registered
    with the stored key, so the TV never shows a pairing prompt. TVs that
    answer the hello handshake return the UUID in milliseconds; webOS 25
    sets ignore hello entirely (belikh/ha-lg-webos-tv#11), in which case
    the timeout degrades to None and callers fall back to the MAC address.
    Never raises: the UUID is optional enrichment.
    """
    if not client_key:
        return None
    client = await make_runtime_client(
        hass, host, client_key, get_hello_info=True, states=[]
    )
    try:
        await asyncio.wait_for(client.connect(), HELLO_PROBE_TIMEOUT)
    except Exception:  # noqa: BLE001 - optional enrichment only
        release_client(client)
        return None
    device_uuid = (client.hello_info or {}).get("deviceUUID")
    client.clear_state_update_callbacks()
    with suppress(Exception):
        await asyncio.wait_for(client.disconnect(), DISCONNECT_TIMEOUT)
    if isinstance(device_uuid, str) and device_uuid:
        return device_uuid
    return None


def release_client(client: WebOsClient | None) -> None:
    """Abandon a (possibly zombie) client without awaiting its teardown.

    Cancelling the connect task is best-effort — the library may swallow
    the cancellation, but its closeout only mutates its own object, which
    callers are about to stop referencing.
    """
    if client is None:
        return
    if (task := client.connect_task) is not None and not task.done():
        task.cancel()


async def async_connect_with_manifest_fallback(
    client: WebOsClient,
    *,
    make_unsigned: Callable[[], Awaitable[WebOsClient]],
    connect_timeout: float,
    prepare: Callable[[WebOsClient], Awaitable[None]] | None = None,
    verify: bool = True,
) -> WebOsClient:
    """Connect ``client``, retrying once with the unsigned manifest.

    webOS 26 (firmware 43.x) rejects the legacy signed manifest with a
    ``403 Pairing rejected: blacklisted certificate detected`` registration
    error. bscpylgtv discards that frame: without a stored key it raises
    ``PyLGTVPairException("Unable to pair")``, and with a stored key it can
    even report success over a dead registration. Both signals are caught
    here: the connection is abandoned and retried once with the merged
    unsigned manifest (``build_unsigned_manifest``).

    TVs that still accept the signed manifest are untouched — the retry
    only happens after a rejection, so elevated signed-only permissions
    (``WRITE_SETTINGS``, used for picture settings) are preserved. A
    transport failure (TV off/unreachable) is re-raised without a retry,
    so an unreachable TV still costs a single connect timeout.

    ``prepare`` (optional) runs on every candidate before it connects, to
    re-register the state-update callback. ``verify`` runs a real,
    bounded request after connect to catch a silently rejected
    registration; disable it for pairing, where no key exists yet.
    Returns the connected client, or raises the last error when both
    manifests were rejected.
    """
    candidate = client
    unsigned = False
    last_error: Exception | None = None
    while True:
        if prepare is not None:
            await prepare(candidate)
        try:
            await asyncio.wait_for(candidate.connect(), connect_timeout)
        except PyLGTVPairException as err:
            last_error = err
        except Exception:
            release_client(candidate)
            raise
        else:
            if not verify:
                return candidate
            try:
                await asyncio.wait_for(candidate.get_power_state(), PROBE_TIMEOUT)
            except Exception as err:  # noqa: BLE001 - dead registration
                last_error = err
            else:
                return candidate
        release_client(candidate)
        if unsigned:
            assert last_error is not None
            raise last_error
        LOGGER.debug(
            "Signed manifest rejected (%s); retrying with the unsigned manifest",
            last_error,
        )
        candidate = await make_unsigned()
        unsigned = True


@callback
def update_client_key(
    hass: HomeAssistant, entry: BscpylgtvConfigEntry, client: WebOsClient
) -> None:
    """Persist a rotated client key into entry.data (never mutate in place)."""
    if client.client_key and client.client_key != entry.data.get(CONF_CLIENT_KEY):
        LOGGER.debug("Updating client key for host %s", entry.data[CONF_HOST])
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_CLIENT_KEY: client.client_key}
        )


_MAC_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def extract_mac(software_info: Mapping[str, Any] | None) -> str | None:
    """Return ``software_info['device_id']`` when it is a valid MAC.

    Shared by the config flow (identity fallback) and the coordinator
    (wake-on-LAN self-heal). Not every set reports a MAC here; anything
    that does not match the pattern is treated as absent.
    """
    device_id = (software_info or {}).get("device_id")
    if isinstance(device_id, str) and _MAC_PATTERN.fullmatch(device_id):
        return device_id
    return None


@callback
def update_mac_address(
    hass: HomeAssistant, entry: BscpylgtvConfigEntry, client: WebOsClient
) -> None:
    """Self-heal the wake-on-LAN MAC from ``software_info['device_id']``."""
    device_id = extract_mac(client.software_info)
    if device_id and device_id != entry.data.get(CONF_MAC):
        LOGGER.debug("Updating MAC address for host %s", entry.data[CONF_HOST])
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_MAC: device_id}
        )


class BscpylgtvCoordinator(DataUpdateCoordinator[None]):
    """Push coordinator with a reconnect/zombie watchdog for one TV."""

    config_entry: BscpylgtvConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: BscpylgtvConfigEntry,
        client: WebOsClient,
    ) -> None:
        """Initialize the coordinator with the entry's first client."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=config_entry.title,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self._reconnect_lock = asyncio.Lock()

    @property
    def turn_on_available(self) -> bool:
        """Whether a wake-on-LAN path exists (gates TURN_ON, AD-8)."""
        return self.config_entry.data.get(CONF_MAC) is not None

    async def async_handle_update(self, client: WebOsClient) -> None:
        """Handle a state update pushed by the TV.

        Registered directly as the library callback. bscpylgtv 0.5.4 wraps
        callback results itself (``asyncio.create_task`` in the teardown
        closeout, ``asyncio.gather`` on push), so this must stay a plain
        coroutine function — returning a Task would make the library's
        ``create_task`` raise. On 0.5.3 the same shape crashed teardown on
        Python 3.11+; this integration pins 0.5.4.

        Exception-shielded: the library's ``callback_handler`` only catches
        ``CancelledError``, so a callback exception would kill the
        subscription task permanently. The callback is idempotent and
        re-entrant (registration on a connected client fires it instantly).
        """
        try:
            if self.last_update_success:
                # A failing connection also fires callbacks during teardown;
                # don't flip entities back to available on that noise.
                self.async_set_updated_data(None)
        except Exception:  # noqa: BLE001 - shield the subscription task
            LOGGER.exception("Unexpected error in state update callback")

    async def _async_is_alive(self) -> bool:
        """Probe the connection with a real, timeout-bounded request."""
        if not self.client.is_connected():
            return False
        try:
            await asyncio.wait_for(self.client.get_power_state(), PROBE_TIMEOUT)
        except Exception:  # noqa: BLE001 - any failure means an unusable link
            return False
        return True

    async def _async_make_client(
        self, *, unsigned_manifest: bool = False
    ) -> WebOsClient:
        """Build a fresh runtime client, reading the current stored key."""
        return await make_runtime_client(
            self.hass,
            self.config_entry.data[CONF_HOST],
            self.config_entry.data.get(CONF_CLIENT_KEY),
            unsigned_manifest=unsigned_manifest,
        )

    async def _async_prepare_client(self, client: WebOsClient) -> None:
        """Register the push callback before a client connects.

        The library clears state_update_callbacks in its teardown, so every
        fresh client needs it re-registered BEFORE the connect attempt
        (plan AD-2). Plain coroutine function: bscpylgtv 0.5.4 wraps
        callback results itself (create_task on teardown).
        """
        await client.register_state_update_callback(self.async_handle_update)

    async def _async_reconnect(self) -> bool:
        """Abandon the current client and connect a fresh one (lock held)."""
        release_client(self.client)
        self.client = await self._async_make_client()
        try:
            self.client = await async_connect_with_manifest_fallback(
                self.client,
                make_unsigned=lambda: self._async_make_client(unsigned_manifest=True),
                connect_timeout=RECONNECT_TIMEOUT,
                prepare=self._async_prepare_client,
            )
        except PyLGTVPairException as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="auth_failed",
                translation_placeholders={"device": self.name},
            ) from err
        except BSCP_CONNECTION_EXCEPTIONS:
            # The helper already abandoned the failed candidate(s); the
            # next watchdog tick builds another fresh client.
            return False
        update_client_key(self.hass, self.config_entry, self.client)
        update_mac_address(self.hass, self.config_entry, self.client)
        return True

    async def _async_update_data(self) -> None:
        """Watchdog tick: probe liveness, reconnect dead/zombie connections."""
        if await self._async_is_alive():
            return
        async with self._reconnect_lock:
            # Another task may have reconnected while we waited for the lock.
            if await self._async_is_alive():
                return
            connected = await self._async_reconnect()
        if (
            not connected
            and not self.turn_on_available
            and self.config_entry.state is ConfigEntryState.LOADED
        ):
            # No wake path and the entry was healthy before: surface it.
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="device_unavailable",
                translation_placeholders={"device": self.name},
            )
        # Otherwise stay quiet: with a wake-on-LAN path the entities stay
        # available showing OFF (webostv semantics, MAC ~= turn-on action).

    async def async_recover(self) -> None:
        """Best-effort recovery pass before a command retry (cmd decorator).

        Pairing failures surface as ``ConfigEntryAuthFailed`` (reauth UI);
        connection failures are suppressed so the retry can fail with a
        translated communication error instead.
        """
        async with self._reconnect_lock:
            if not await self._async_is_alive():
                try:
                    await self._async_reconnect()
                except BSCP_CONNECTION_EXCEPTIONS:
                    LOGGER.debug("Recovery reconnect failed; retry will fail")

    async def async_take_screenshot(
        self, filename: str | None = None
    ) -> dict[str, str]:
        """Capture a screenshot; returns ``{"image": <base64 jpg>}``.

        Payload shapes vary by model/firmware: base64 JPEG under
        ``image`` (older sets), or an ``imageUri`` that is either a
        ``data:`` URI or an ``https://`` resource on the TV's
        self-signed certificate (verified on a CX OLED48CXPTA, webOS
        04.40.16 — no ``image`` key at all). ``filename`` writes the
        decoded JPEG via the executor (relative paths resolve against
        the config directory).
        """
        payload = await self.client.take_screenshot()
        image = await self._async_screenshot_image(payload)
        if filename is not None:
            try:
                await self.hass.async_add_executor_job(
                    _write_screenshot_file,
                    self.hass.config.config_dir,
                    filename,
                    image,
                )
            except OSError as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="screenshot_write_failed",
                    translation_placeholders={
                        "filename": filename,
                        "error": str(err),
                    },
                ) from err
        return {"image": base64.b64encode(image).decode("ascii")}

    async def _async_screenshot_image(self, payload: Any) -> bytes:
        """Extract JPEG bytes from any known screenshot payload shape."""
        if isinstance(payload, dict):
            b64 = payload.get("image")
            if isinstance(b64, str) and b64:
                return base64.b64decode(b64)
            uri = payload.get("imageUri")
            if isinstance(uri, str) and uri:
                if uri.startswith("data:"):
                    return base64.b64decode(uri.partition(",")[2])
                if uri.startswith(("http://", "https://")):
                    return await self._async_fetch_screenshot(uri)
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="communication_error",
            translation_placeholders={
                "name": self.name,
                "func": "async_take_screenshot",
                "error": "no image data in screenshot payload",
            },
        )

    async def _async_fetch_screenshot(self, url: str) -> bytes:
        """Fetch the screenshot resource (self-signed cert → verify off)."""
        session = async_get_clientsession(self.hass)
        try:
            response = await session.get(url, ssl=False)
            response.raise_for_status()
            return await response.read()
        except Exception as err:  # noqa: BLE001 - translated below
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={
                    "name": self.name,
                    "func": "async_take_screenshot",
                    "error": f"fetching {url}: {err}",
                },
            ) from err


type BscpylgtvConfigEntry = ConfigEntry[BscpylgtvCoordinator]


def _write_screenshot_file(config_dir: str, filename: str, data: bytes) -> None:
    """Write screenshot bytes to disk (executor only; blocking I/O)."""
    path = Path(filename)
    if not path.is_absolute():
        path = Path(config_dir) / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
