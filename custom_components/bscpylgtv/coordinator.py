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

from .const import (
    BSCP_CONNECTION_EXCEPTIONS,
    CONF_CLIENT_KEY,
    CONF_MAC,
    DEFAULT_STATES,
    DOMAIN,
    LOGGER,
    PROBE_TIMEOUT,
    RECONNECT_TIMEOUT,
    SCAN_INTERVAL,
)
from .key_storage import InMemoryKeyStorage


async def make_runtime_client(
    hass: HomeAssistant, host: str, client_key: str | None
) -> WebOsClient:
    """Build a runtime client with the AD-2 kwargs.

    The constructor builds an SSL context (blocking I/O), so it always
    runs in an executor. ``InMemoryKeyStorage`` is always injected: the
    library writes freshly paired keys through ``storage.set_key`` during
    registration and would raise ``AttributeError`` without it.
    """
    return await hass.async_add_executor_job(
        functools.partial(
            WebOsClient,
            host,
            client_key=client_key,
            storage=InMemoryKeyStorage(client_key),
            timeout_connect=10,
            connect_retry_attempts=1,
            ping_interval=10,
            volume_step_delay_ms=100,
            get_hello_info=True,
            states=DEFAULT_STATES,
        )
    )


async def make_pairing_client(hass: HomeAssistant, host: str) -> WebOsClient:
    """Build a fresh-pairing client for the config flow (AD-2).

    Consumed read-only by the config flow (Cluster B): empty storage (the
    library stores the new key there and exposes it as ``client.client_key``),
    PROMPT pairing (never PIN — the PIN path does blocking ``input()``), no
    state subscriptions, hello info requested for the device UUID.
    """
    return await hass.async_add_executor_job(
        functools.partial(
            WebOsClient,
            host,
            storage=InMemoryKeyStorage(None),
            pairing_type="PROMPT",
            timeout_connect=10,
            connect_retry_attempts=1,
            states=[],
            get_hello_info=True,
        )
    )


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


@callback
def update_mac_address(
    hass: HomeAssistant, entry: BscpylgtvConfigEntry, client: WebOsClient
) -> None:
    """Self-heal the wake-on-LAN MAC from ``software_info['device_id']``."""
    device_id = (client.software_info or {}).get("device_id")
    if (
        device_id
        and _MAC_PATTERN.fullmatch(device_id)
        and device_id != entry.data.get(CONF_MAC)
    ):
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

    def state_update_task(self, client: WebOsClient) -> asyncio.Task[None]:
        """Schedule one push update and return the Task — never a coroutine.

        bscpylgtv invokes state-update callbacks in three places: an
        immediate ``await callback(self)`` on registration and
        ``asyncio.gather`` on every push (both accept coroutines and
        Tasks), and the ``connect_handler`` teardown closeout, which
        collects ``callback(self)`` results into a set and hands it to
        ``asyncio.wait``. Raw coroutines make ``asyncio.wait`` raise
        ``TypeError("Passing coroutines is forbidden")`` on Python
        3.11+, which kills the library's teardown: ``disconnect()``
        dies mid-call and the client never cleans up (observed on real
        hardware; upstream fix pending chros73/bscpylgtv PR). Returning
        a Task keeps every call site working on all supported Pythons.
        """
        return asyncio.get_running_loop().create_task(self.async_handle_update(client))

    async def async_handle_update(self, client: WebOsClient) -> None:
        """Handle a state update pushed by the TV.

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

    async def _async_make_client(self) -> WebOsClient:
        """Build a fresh runtime client, reading the current stored key."""
        return await make_runtime_client(
            self.hass,
            self.config_entry.data[CONF_HOST],
            self.config_entry.data.get(CONF_CLIENT_KEY),
        )

    async def _async_reconnect(self) -> bool:
        """Abandon the current client and connect a fresh one (lock held)."""
        release_client(self.client)
        self.client = await self._async_make_client()
        # The library clears state_update_callbacks in its teardown, so the
        # callback must be re-registered on every fresh client BEFORE the
        # connect attempt (plan AD-2). state_update_task (not
        # async_handle_update): the library's teardown closeout feeds
        # callback results to asyncio.wait, which rejects raw coroutines.
        await self.client.register_state_update_callback(self.state_update_task)
        try:
            await asyncio.wait_for(self.client.connect(), RECONNECT_TIMEOUT)
        except PyLGTVPairException as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="auth_failed",
                translation_placeholders={"device": self.name},
            ) from err
        except BSCP_CONNECTION_EXCEPTIONS:
            # Abandon the failed client too: if the bound was hit by
            # wait_for, its connect handler may still be winding down.
            # The next watchdog tick builds another fresh client.
            release_client(self.client)
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
