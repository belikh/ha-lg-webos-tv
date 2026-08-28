"""Tests for the notify entity (plan AC-23)."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from bscpylgtv.endpoints import SHOW_MESSAGE
from bscpylgtv.exceptions import PyLGTVCmdError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .conftest import get_entity

# Re-use the long-lived setup fixture.
from .conftest import integration as _integration  # noqa: F401

NOTIFY = "notify.lg_webos_tv_oled55c2_notifications"


def _entity(hass: HomeAssistant) -> Any:
    return get_entity(hass, "notify", NOTIFY)


def _toast(client: Any) -> tuple[str, dict[str, Any]]:
    """Return the single (endpoint, payload) toast request on the client."""
    assert client.request.await_count == 1
    endpoint, payload = client.request.await_args.args
    return endpoint, payload


# ---------------------------------------------------------------------------
# Toasts via the HA service
# ---------------------------------------------------------------------------


async def test_send_message_via_service(integration: Any) -> None:
    hass = integration.coordinator.hass
    await hass.services.async_call(
        "notify",
        "send_message",
        {"entity_id": NOTIFY, "message": "Dinner is ready!"},
        blocking=True,
    )
    endpoint, payload = _toast(integration.tv.client)
    assert endpoint == SHOW_MESSAGE
    assert payload == {
        "message": "Dinner is ready!",
        "iconData": "",
        "iconExtension": "",
    }


async def test_title_prefixed_to_message(integration: Any) -> None:
    """A webOS toast has no title element: "<title>: <message>"."""
    hass = integration.coordinator.hass
    await hass.services.async_call(
        "notify",
        "send_message",
        {"entity_id": NOTIFY, "message": "Fire", "title": "Alert"},
        blocking=True,
    )
    _, payload = _toast(integration.tv.client)
    assert payload["message"] == "Alert: Fire"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


async def test_device_off_raises_notify_device_off(integration: Any) -> None:
    hass = integration.coordinator.hass
    integration.tv.power_state = {"state": "Power Off"}
    integration.tv.push_update()
    await hass.async_block_till_done()
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "notify",
            "send_message",
            {"entity_id": NOTIFY, "message": "Hello"},
            blocking=True,
        )
    assert err.value.translation_key == "notify_device_off"
    integration.tv.client.request.assert_not_awaited()


async def test_communication_error_translated(integration: Any) -> None:
    hass = integration.coordinator.hass
    integration.tv.client.request = AsyncMock(  # type: ignore[method-assign]
        side_effect=PyLGTVCmdError("socket gone")
    )
    with pytest.raises(HomeAssistantError) as err:
        await _entity(hass).async_send_message("Hello")
    assert err.value.translation_key == "notify_communication_error"
    assert "socket gone" in str(err.value)


# ---------------------------------------------------------------------------
# Icon via direct entity call (service schema strips data)
# ---------------------------------------------------------------------------


async def test_icon_read_in_executor_and_sent(integration: Any) -> None:
    hass = integration.coordinator.hass
    icon = Path(hass.config.config_dir) / "www" / "dinner.png"
    icon.parent.mkdir(parents=True, exist_ok=True)
    content = b"\x89PNG\r\n\x1a\nFAKEPNG"
    icon.write_bytes(content)
    await _entity(hass).async_send_message("Dinner", data={"icon": str(icon)})
    _, payload = _toast(integration.tv.client)
    assert payload["iconData"] == base64.b64encode(content).decode("ascii")
    assert payload["iconExtension"] == "png"


async def test_icon_without_extension(integration: Any) -> None:
    hass = integration.coordinator.hass
    icon = Path(hass.config.config_dir) / "icon"
    icon.write_bytes(b"raw")
    await _entity(hass).async_send_message("Hi", data={"icon": str(icon)})
    _, payload = _toast(integration.tv.client)
    assert payload["iconExtension"] == ""


async def test_missing_icon_raises_notify_icon_not_found(integration: Any) -> None:
    hass = integration.coordinator.hass
    with pytest.raises(HomeAssistantError) as err:
        await _entity(hass).async_send_message(
            "Hi", data={"icon": "/nonexistent/icon.png"}
        )
    assert err.value.translation_key == "notify_icon_not_found"
    integration.tv.client.request.assert_not_awaited()
