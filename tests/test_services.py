"""Tests for the six bscpylgtv entity services (plan AD-14, AC-6/19/24)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from bscpylgtv.endpoints import SHOW_MESSAGE  # noqa: F401 - used in AC-6 docs
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.setup import async_setup_component

from custom_components.bscpylgtv.const import DOMAIN

from .conftest import FAKE_JPEG, FAKE_JPEG_B64

# Re-use the long-lived setup fixture.
from .conftest import integration as _integration  # noqa: F401

MP = "media_player.lg_webos_tv_oled55c2"

SERVICES = (
    "button",
    "command",
    "select_sound_output",
    "launch_app",
    "take_screenshot",
    "set_settings",
)

# Every library command the raw-SSAP path must NOT getattr-dispatch to.
_DISPATCH_TARGETS = (
    "launch_app",
    "launch_app_with_params",
    "set_input",
    "set_channel",
    "set_volume",
    "set_mute",
    "play",
    "pause",
    "stop",
    "reboot",
    "turn_screen_off",
    "turn_screen_on",
    "set_settings",
    "change_sound_output",
    "button",
    "click",
    "move",
    "scroll",
    "insert_text",
    "take_screenshot",
)


async def _call(
    hass: HomeAssistant,
    service: str,
    data: dict[str, Any] | None = None,
    *,
    return_response: bool = False,
) -> Any:
    return await hass.services.async_call(
        DOMAIN,
        service,
        {"entity_id": MP, **(data or {})},
        blocking=True,
        return_response=return_response,
    )


# ---------------------------------------------------------------------------
# Registration (AC-24)
# ---------------------------------------------------------------------------


async def test_services_registered_without_entries(hass: HomeAssistant) -> None:
    """async_setup registers all six services even with zero config entries."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    for service in SERVICES:
        assert hass.services.has_service(DOMAIN, service), service


# ---------------------------------------------------------------------------
# button
# ---------------------------------------------------------------------------


async def test_button_service_presses(integration: Any) -> None:
    hass = integration.coordinator.hass
    await _call(hass, "button", {"button": "INFO"})
    integration.tv.client.button.assert_awaited_once_with("INFO")


async def test_button_service_invalid_name(integration: Any) -> None:
    """An unknown button raises unknown_button (validated against BUTTONS)."""
    hass = integration.coordinator.hass
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "button", {"button": "BOGUS"})
    assert err.value.translation_key == "unknown_button"
    assert err.value.translation_placeholders == {"button": "BOGUS"}


async def test_button_service_blocked_when_device_off(integration: Any) -> None:
    hass = integration.coordinator.hass
    integration.tv.power_state = {"state": "Power Off"}
    integration.tv.push_update()
    await hass.async_block_till_done()
    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, "button", {"button": "HOME"})
    assert err.value.translation_key == "device_off"
    integration.tv.client.button.assert_not_awaited()


# ---------------------------------------------------------------------------
# command (AC-6: raw SSAP, never getattr dispatch)
# ---------------------------------------------------------------------------


async def test_command_sends_raw_ssap_with_payload(integration: Any) -> None:
    """The endpoint + payload reach client.request verbatim."""
    hass = integration.coordinator.hass
    payload = {"target": "https://www.youtube.com"}
    response = await _call(
        hass,
        "command",
        {"command": "ssap://system.launcher/open", "payload": payload},
        return_response=True,
    )
    integration.tv.client.request.assert_awaited_once_with(
        "ssap://system.launcher/open", payload=payload
    )
    # Entity-service responses are keyed by the target entity id.
    assert response == {MP: {"returnValue": True, "payload": {}}}


async def test_command_without_payload(integration: Any) -> None:
    hass = integration.coordinator.hass
    await _call(hass, "command", {"command": "ssap://api/getServiceList"})
    integration.tv.client.request.assert_awaited_once_with(
        "ssap://api/getServiceList", payload=None
    )


async def test_command_method_name_is_not_dispatched(integration: Any) -> None:
    """A v1-style method name goes to the wire as-is; no library call."""
    hass = integration.coordinator.hass
    client = integration.tv.client
    await _call(hass, "command", {"command": "launch_app"})
    client.request.assert_awaited_once_with("launch_app", payload=None)
    # NO getattr-style dispatch: no other client command fired.
    for name in _DISPATCH_TARGETS:
        attr = getattr(client, name)
        assert isinstance(attr, AsyncMock), name
        assert attr.await_count == 0, name


# ---------------------------------------------------------------------------
# select_sound_output
# ---------------------------------------------------------------------------


async def test_select_sound_output_awaits_change(integration: Any) -> None:
    hass = integration.coordinator.hass
    response = await _call(
        hass, "select_sound_output", {"sound_output": "external_arc"}
    )
    integration.tv.client.change_sound_output.assert_awaited_once_with("external_arc")
    assert response is None


# ---------------------------------------------------------------------------
# launch_app
# ---------------------------------------------------------------------------


async def test_launch_app_simple(integration: Any) -> None:
    hass = integration.coordinator.hass
    await _call(hass, "launch_app", {"app_id": "youtube.2016"})
    integration.tv.client.launch_app.assert_awaited_once_with("youtube.2016")
    integration.tv.client.launch_app_with_params.assert_not_awaited()


async def test_launch_app_with_params(integration: Any) -> None:
    hass = integration.coordinator.hass
    params = {"contentTarget": "https://www.youtube.com/watch?v=x"}
    await _call(hass, "launch_app", {"app_id": "youtube.2016", "params": params})
    integration.tv.client.launch_app_with_params.assert_awaited_once_with(
        "youtube.2016", params
    )
    integration.tv.client.launch_app.assert_not_awaited()


# ---------------------------------------------------------------------------
# take_screenshot (AC-19)
# ---------------------------------------------------------------------------


async def test_take_screenshot_returns_base64_response(integration: Any) -> None:
    hass = integration.coordinator.hass
    response = await _call(hass, "take_screenshot", return_response=True)
    integration.tv.client.take_screenshot.assert_awaited_once()
    assert response == {MP: {"image": FAKE_JPEG_B64}}


async def test_take_screenshot_writes_jpeg_file(integration: Any) -> None:
    """A filename is resolved against the config dir and gets JPEG magic."""
    hass = integration.coordinator.hass
    response = await _call(
        hass, "take_screenshot", {"filename": "www/tv_shot.jpg"}, return_response=True
    )
    path = Path(hass.config.path("www", "tv_shot.jpg"))
    assert await hass.async_add_executor_job(path.is_file)
    data = await hass.async_add_executor_job(path.read_bytes)
    assert data[:2] == b"\xff\xd8"  # JPEG magic
    assert data == FAKE_JPEG
    assert response == {MP: {"image": FAKE_JPEG_B64}}


async def test_take_screenshot_write_failure(integration: Any) -> None:
    hass = integration.coordinator.hass
    with (
        patch(
            "custom_components.bscpylgtv.media_player.BscpylgtvMediaPlayer"
            "._write_screenshot_file",
            side_effect=OSError("disk full"),
        ),
        pytest.raises(HomeAssistantError) as err,
    ):
        await _call(hass, "take_screenshot", {"filename": "www/broken.jpg"})
    assert err.value.translation_key == "screenshot_write_failed"


async def test_take_screenshot_without_image_data(integration: Any) -> None:
    hass = integration.coordinator.hass
    integration.tv.client.take_screenshot = AsyncMock(return_value={})
    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, "take_screenshot", return_response=True)
    assert err.value.translation_key == "communication_error"


# ---------------------------------------------------------------------------
# set_settings
# ---------------------------------------------------------------------------


async def test_set_settings_luna_write(integration: Any) -> None:
    hass = integration.coordinator.hass
    await _call(
        hass, "set_settings", {"category": "picture", "settings": {"backlight": 55}}
    )
    integration.tv.client.set_settings.assert_awaited_once_with(
        "picture", {"backlight": 55}
    )
