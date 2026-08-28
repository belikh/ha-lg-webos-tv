"""Shared fixtures for the bscpylgtv integration tests (plan AD-19).

The mock client is a hand-written async class (NOT an AsyncMock of the
library class): entity/coordinator code reads live attributes
(``power_state``, ``apps`` …) and swaps client objects on reconnect, so
the mock must be a real object with identity semantics and library-real
data shapes.
"""

from __future__ import annotations

import asyncio
import base64
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

# Make the repo root importable so ``import custom_components.bscpylgtv``
# (and the bscpylgtv library) resolve when pytest runs from anywhere.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

pytest_plugins = ["pytest_homeassistant_custom_component"]  # noqa: ICN001

# JPEG magic bytes used by the fake screenshot payload.
FAKE_JPEG = b"\xff\xd8\xff\xe0FAKEJPEGDATA"
FAKE_JPEG_B64 = base64.b64encode(FAKE_JPEG).decode("ascii")

# A second JPEG so "screenshot changed" assertions are possible.
FAKE_JPEG_2 = b"\xff\xd8\xff\xe0OTHERJPEGBYTES"
FAKE_JPEG_2_B64 = base64.b64encode(FAKE_JPEG_2).decode("ascii")


class TVSimulator:
    """Shared per-test TV state.

    Every ``MockWebOsClient`` created for one TV reads its state from the
    same simulator instance, mirroring the real world: reconnects create
    fresh client objects that observe the same physical TV. Tests mutate
    the simulator (``tv.volume = 30``) and push coordinator updates via
    ``tv.push_update()``.
    """

    def __init__(self, host: str = "192.168.1.42") -> None:
        self.host = host
        self.device_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        self.mac = "AA:BB:CC:DD:EE:FF"
        # Exception (or exception instance) raised by client.connect().
        self.connect_exception: BaseException | None = None
        # All clients ever created for this TV (index 0 = first).
        self.clients: list[MockWebOsClient] = []

        # Live state (real library shapes; see webos_client.py).
        self.power_state = {"state": "Active"}
        self.current_appId = "youtube.2016"
        self.muted = False
        self.volume = 12
        self.sound_output = "tv_speaker"
        self.system_info = {"modelName": "OLED55C2"}
        self.software_info = {
            "device_id": self.mac,
            "major_ver": "03",
            "minor_ver": "30.15",
        }
        self.hello_info = {"deviceUUID": self.device_uuid}
        self.picture_settings: dict[str, Any] = {
            "backlight": 50,
            "contrast": 80,
            "brightness": 50,
            "color": 50,
            "sharpness": "10",
            "colorTemperature": "0",
        }
        self.apps = {
            "youtube.2016": {
                "id": "youtube.2016",
                "title": "YouTube",
                "icon": "/usr/share/icons/youtube.png",
                "largeIcon": "http://192.168.1.42:3000/icon/youtube.png",
            },
            "com.webos.app.livetv": {
                "id": "com.webos.app.livetv",
                "title": "Live TV",
                "icon": "/usr/share/icons/livetv.png",
            },
            "netflix": {
                "id": "netflix",
                "title": "Netflix",
                "icon": "/usr/share/icons/netflix.png",
            },
        }
        self.inputs = {
            "com.webos.app.hdmi1": {
                "appId": "com.webos.app.hdmi1",
                "label": "HDMI 1",
                "id": "com.webos.app.hdmi1",
                "icon": "http://192.168.1.42:3000/icon/hdmi1.png",
            },
            "com.webos.app.hdmi2": {
                "appId": "com.webos.app.hdmi2",
                "label": "HDMI 2",
                "id": "com.webos.app.hdmi2",
                "icon": "http://192.168.1.42:3000/icon/hdmi2.png",
            },
        }
        self.channels = [
            {"channelId": "ch1", "channelNumber": "5.1", "channelName": "RTL"},
            {"channelId": "ch2", "channelNumber": "10", "channelName": "ZDF HD"},
            {"channelId": "ch3", "channelNumber": "20", "channelName": " Arte"},
        ]
        self.current_channel: dict[str, Any] | None = None

    def create_client(
        self,
        host: str | None = None,
        client_key: str | None = "stored-key",
        **kwargs: Any,
    ) -> MockWebOsClient:
        """Create (and register) a fresh mock client for this TV."""
        client = MockWebOsClient(
            host if host is not None else self.host,
            tv=self,
            client_key=client_key,
            **kwargs,
        )
        self.clients.append(client)
        return client

    def push_update(self) -> None:
        """Fire every registered state callback on connected clients.

        Mirrors the library: a TV push invokes the callbacks of the
        connected client only.
        """
        for client in self.clients:
            if client.is_connected():
                client.fire_state_update_callbacks()

    @property
    def client(self) -> MockWebOsClient:
        """Return the most recently created client (the coordinator's)."""
        return self.clients[-1]

    def disconnect_all(self) -> None:
        """Drop the socket from the TV side (zombie/loss scenarios)."""
        for client in self.clients:
            client._connected = False  # noqa: SLF001 - test helper


class MockWebOsClient:
    """A hand-written async stand-in for ``bscpylgtv.WebOsClient``.

    State lives on the shared ``TVSimulator``; command methods are
    per-instance ``AsyncMock``s with sensible return payloads so tests
    can assert calls and rewire outcomes (``side_effect``).
    """

    def __init__(
        self,
        host: str,
        tv: TVSimulator | None = None,
        client_key: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.tv = tv if tv is not None else TVSimulator(host)
        self.host = host
        self.client_key = client_key
        # Constructor kwargs captured for factory assertions (AD-2).
        self.init_kwargs: dict[str, Any] = kwargs
        self._connected = False
        # The library stores its connect task here; release_client()
        # cancels it when abandoning a zombie. The mock keeps it simple.
        self.connect_task: asyncio.Future[None] | None = None
        self.state_update_callbacks: list[
            Callable[[MockWebOsClient], Awaitable[None]]
        ] = []

        ok = {"returnValue": True}
        # Power / screen
        self.turn_screen_off = AsyncMock(return_value=ok)
        self.turn_screen_on = AsyncMock(return_value=ok)
        self.reboot = AsyncMock(return_value=ok)
        self.get_power_state = AsyncMock(
            return_value={
                "state": self.tv.power_state.get("state"),
                "returnValue": True,
            }
        )
        # Apps / inputs / channels
        self.launch_app = AsyncMock(return_value=ok)
        self.launch_app_with_params = AsyncMock(return_value=ok)
        self.set_input = AsyncMock(return_value=ok)
        self.set_channel = AsyncMock(return_value=ok)
        self.channel_up = AsyncMock(return_value=ok)
        self.channel_down = AsyncMock(return_value=ok)
        self.get_apps = AsyncMock(return_value=[])
        self.get_inputs = AsyncMock(return_value=[])
        # Audio / playback
        self.set_volume = AsyncMock(return_value=ok)
        self.volume_up = AsyncMock(return_value=ok)
        self.volume_down = AsyncMock(return_value=ok)
        self.set_mute = AsyncMock(return_value=ok)
        self.play = AsyncMock(return_value=ok)
        self.pause = AsyncMock(return_value=ok)
        self.stop = AsyncMock(return_value=ok)
        self.fast_forward = AsyncMock(return_value=ok)
        self.rewind = AsyncMock(return_value=ok)
        self.change_sound_output = AsyncMock(return_value=ok)
        # Settings (live views: read what the TV currently reports)
        self.get_picture_settings = AsyncMock(
            side_effect=lambda keys=None: {
                key: self.tv.picture_settings.get(key) for key in (keys or [])
            }
        )
        self.get_system_settings = AsyncMock(
            return_value={"settings": {"pictureMode": ["normal", "vivid", "cinema"]}}
        )
        self.set_settings = AsyncMock(return_value=ok)
        self.set_system_settings = AsyncMock(return_value=ok)
        self.enable_tpc_or_gsr = AsyncMock(return_value=ok)
        # Info fetches (config flow reads these directly)
        self.get_system_info = AsyncMock(return_value=dict(self.tv.system_info))
        self.get_software_info = AsyncMock(return_value=dict(self.tv.software_info))
        # Media
        self.take_screenshot = AsyncMock(return_value={"image": FAKE_JPEG_B64})
        # Raw SSAP + notify
        self.request = AsyncMock(return_value={"returnValue": True, "payload": {}})
        # Pointer / IME
        self.click = AsyncMock(return_value=ok)
        self.move = AsyncMock(return_value=ok)
        self.scroll = AsyncMock(return_value=ok)
        self.insert_text = AsyncMock(return_value=ok)
        # Buttons: validated against the real library BUTTONS tuple.
        self.button = AsyncMock(side_effect=self._validate_button)

    @staticmethod
    def _validate_button(name: str, checkValid: bool = True) -> None:
        """Raise like the library for unknown buttons (checkValid)."""
        from bscpylgtv.buttons import BUTTONS

        if checkValid and str(name) not in BUTTONS:
            raise ValueError(f"button {name} is not valid")

    # --------------------------------------------------------------
    # Connection lifecycle
    # --------------------------------------------------------------
    async def connect(self) -> None:
        """Connect: raise the configured failure, else mark connected.

        Library-faithful (webos_client.py): a successful handshake fires
        the registered state callbacks once at the end of connect. This
        post-reconnect re-sync is what fixes issue #9 symptom 3 (a value
        that changed on the TV while unreachable must surface when it
        returns — v1 kept the stale default because its subscription had
        died; see the PR #8 dict-iteration fix).
        """
        self._connected = True
        if (exc := self.tv.connect_exception) is not None:
            self._connected = False
            raise exc
        for callback in list(self.state_update_callbacks):
            await callback(self)

    async def disconnect(self) -> None:
        """Disconnect the (healthy) client."""
        self._connected = False

    def is_connected(self) -> bool:
        """Return whether the connect task is alive."""
        return self._connected

    def is_registered(self) -> bool:
        """Return whether a pairing key is present."""
        return self.client_key is not None

    # --------------------------------------------------------------
    # State callbacks (library semantics)
    # --------------------------------------------------------------
    async def register_state_update_callback(
        self, callback: Callable[[MockWebOsClient], Awaitable[None]]
    ) -> None:
        """Register a callback; fired immediately when already connected."""
        self.state_update_callbacks.append(callback)
        if self._connected:
            await callback(self)

    def unregister_state_update_callback(
        self, callback: Callable[[MockWebOsClient], Awaitable[None]]
    ) -> None:
        """Remove a callback."""
        if callback in self.state_update_callbacks:
            self.state_update_callbacks.remove(callback)

    def clear_state_update_callbacks(self) -> None:
        """Drop all callbacks (library teardown does this too)."""
        self.state_update_callbacks.clear()

    def fire_state_update_callbacks(self) -> None:
        """Schedule every registered callback (sync, from test code).

        Callbacks may be async functions (raw coroutines) or sync
        factories returning an already-scheduled Task — the integration
        registers the latter (library teardown-compat). Schedule only
        what is not already scheduled.
        """
        for callback in list(self.state_update_callbacks):
            result = callback(self)
            if not isinstance(result, asyncio.Task):
                asyncio.get_running_loop().create_task(result)

    # --------------------------------------------------------------
    # Live state (read from the shared TV simulator)
    # --------------------------------------------------------------
    @property
    def power_state(self) -> dict[str, Any]:
        """Return the subscribed power state."""
        return self.tv.power_state

    @property
    def current_appId(self) -> str | None:
        """Return the foreground app id."""
        return self.tv.current_appId

    @property
    def muted(self) -> bool | None:
        """Return the mute state."""
        return self.tv.muted

    @property
    def volume(self) -> int | None:
        """Return the volume."""
        return self.tv.volume

    @property
    def sound_output(self) -> str | None:
        """Return the current sound output."""
        return self.tv.sound_output

    @property
    def system_info(self) -> dict[str, Any]:
        """Return the subscribed system info."""
        return self.tv.system_info

    @property
    def software_info(self) -> dict[str, Any]:
        """Return the subscribed software info."""
        return self.tv.software_info

    @property
    def hello_info(self) -> dict[str, Any]:
        """Return the handshake hello info."""
        return self.tv.hello_info

    @property
    def picture_settings(self) -> dict[str, Any]:
        """Return the subscribed picture settings."""
        return self.tv.picture_settings

    @property
    def apps(self) -> dict[str, Any]:
        """Return the app launch points (dict keyed by app id)."""
        return self.tv.apps

    @property
    def inputs(self) -> dict[str, Any]:
        """Return the external inputs (dict keyed by appId)."""
        return self.tv.inputs

    @property
    def channels(self) -> list[dict[str, Any]] | None:
        """Return the channel lineup."""
        return self.tv.channels

    @property
    def current_channel(self) -> dict[str, Any] | None:
        """Return the tuned channel."""
        return self.tv.current_channel

    @property
    def is_on(self) -> bool:
        """Library ``is_on`` logic on the live power state."""
        state = self.power_state.get("state")
        if state == "Unknown":
            return self.current_appId not in (None, "")
        return state not in (None, "Power Off", "Suspend", "Active Standby")

    @property
    def is_screen_on(self) -> bool:
        """Library ``is_screen_on`` logic."""
        if self.is_on:
            return self.power_state.get("state") != "Screen Off"
        return False


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading the custom integration for every test."""


@pytest.fixture(autouse=True)
def _stub_ssdp_setup():
    """Stub the ssdp dependency setup (opens real network sockets).

    The manifest declares ``dependencies: ["ssdp"]``; PHACC forbids real
    socket use. Discovery behavior is tested directly against
    ``async_step_ssdp`` with a SsdpServiceInfo, so the component itself
    never needs to run.
    """
    from unittest.mock import patch

    with patch("homeassistant.components.ssdp.async_setup", return_value=True):
        yield


@pytest.fixture
def tv() -> TVSimulator:
    """Provide a fresh TV simulator."""
    return TVSimulator()


@pytest.fixture
def mock_client(tv: TVSimulator) -> MockWebOsClient:
    """Provide one connected mock client backed by the simulator."""
    client = tv.create_client()
    client._connected = True  # noqa: SLF001 - test helper
    return client


@pytest.fixture
def hass_config_dir(tmp_path: Path) -> str:
    """Use a clean per-test temporary config dir.

    Deliberately NOT ``hass_tmp_config_dir`` (which copies PHACC's
    ``testing_config``): that copy ships a regular ``custom_components``
    package whose ``__init__.py`` shadows this repo's namespace package
    when Home Assistant mounts the config dir on ``sys.path``
    (``loader._async_mount_config_dir``), breaking
    ``custom_components.bscpylgtv`` imports. A clean dir keeps the repo
    root the only ``custom_components`` provider.
    """
    return str(tmp_path)


def patch_client_factory(tv: TVSimulator) -> Any:
    """Patch the coordinator's WebOsClient construction point.

    ``coordinator.WebOsClient`` is the single construction point used by
    ``make_runtime_client`` (both from ``__init__.async_setup_entry`` and
    the coordinator itself). The config flow imports the factories into
    its own namespace and is patched separately in its tests.
    """
    from unittest.mock import patch

    return patch(
        "custom_components.bscpylgtv.coordinator.WebOsClient",
        side_effect=lambda host, **kwargs: tv.create_client(host, **kwargs),
    )


def build_mock_config_entry(
    hass: Any,
    *,
    host: str = "192.168.1.42",
    unique_id: str | None = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    client_key: str | None = "stored-key",
    mac: str | None = None,
    title: str = "LG WebOS TV OLED55C2",
    version: int = 2,
    minor_version: int = 1,
    data: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
) -> Any:
    """Create + register a MockConfigEntry for one TV."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    if data is None:
        data = {
            k: v
            for k, v in {
                "host": host,
                "client_key": client_key,
                "mac": mac,
            }.items()
            if v is not None
        }
    entry = MockConfigEntry(
        domain="bscpylgtv",
        version=version,
        minor_version=minor_version,
        unique_id=unique_id,
        data=data,
        options=options or {},
        title=title,
    )
    entry.add_to_hass(hass)
    return entry


async def setup_integration(
    hass: Any,
    tv: TVSimulator,
    *,
    entry: Any | None = None,
) -> Any:
    """Drive a config entry to a fully set-up integration.

    The caller is responsible for keeping ``patch_client_factory(tv)``
    active for the duration of the scenario when the watchdog may build
    additional clients (see the ``integration`` fixture for the common
    case).
    """
    if entry is None:
        entry = build_mock_config_entry(hass, host=tv.host)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
async def integration(hass: Any, tv: TVSimulator) -> Any:
    """A fully set-up integration entry, with the factory patch active."""
    from types import SimpleNamespace

    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield SimpleNamespace(
            entry=entry,
            tv=tv,
            coordinator=entry.runtime_data,
            client=tv.client,
        )


def get_entity(hass: Any, domain: str, entity_id: str) -> Any:
    """Return the live entity object for an entity_id."""
    component = hass.data["entity_components"][domain]
    return next(e for e in component.entities if e.entity_id == entity_id)


async def enable_entity(hass: Any, entity_id: str) -> None:
    """Enable a disabled-by-default entity and wait for it to appear."""
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    if entry is not None and entry.disabled_by is not None:
        registry.async_update_entity(entity_id, disabled_by=None)
        # Entity regeneration runs through scheduled tasks; two rounds are
        # needed for the new entity object to be added and initialized.
        await hass.async_block_till_done()
        await hass.async_block_till_done()
    assert hass.states.get(entity_id) is not None, f"{entity_id} did not come back"
