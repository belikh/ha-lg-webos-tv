"""Tests for translation/icon metadata completeness (plan AC-20/23/24)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

COMPONENT_DIR = (
    Path(__file__).resolve().parent.parent / "custom_components" / "bscpylgtv"
)

# Every entity key the integration ships, per platform (plan §3.2).
ENTITY_KEYS: dict[str, set[str]] = {
    "button": {"turn_screen_off", "turn_screen_on", "screenshot", "reboot"},
    "number": {
        "backlight",
        "contrast",
        "brightness",
        "color",
        "sharpness",
        "color_temperature",
    },
    "select": {"picture_mode", "sound_output", "channel"},
    "sensor": {"current_app", "volume", "power_state", "current_channel"},
    "switch": {"tpc", "gsr"},
    "remote": {"remote"},
    "notify": {"notify"},
}

SERVICE_FIELDS: dict[str, set[str]] = {
    "button": {"button"},
    "command": {"command", "payload"},
    "select_sound_output": {"sound_output"},
    "launch_app": {"app_id", "params"},
    "take_screenshot": {"filename"},
    "set_settings": {"category", "settings"},
}

# Mirrors the vol.Required markers in services.py.
SERVICE_REQUIRED: dict[str, set[str]] = {
    "button": {"button"},
    "command": {"command"},
    "select_sound_output": {"sound_output"},
    "launch_app": {"app_id"},
    "take_screenshot": set(),
    "set_settings": {"category", "settings"},
}

EXCEPTION_KEYS = {
    "auth_failed",
    "communication_error",
    "device_off",
    "device_unavailable",
    "source_not_found",
    "unknown_button",
    "channel_not_found",
    "notify_device_off",
    "notify_communication_error",
    "notify_icon_not_found",
    "screenshot_write_failed",
    "invalid_mac",
}


def _load_json(relative: str) -> dict[str, Any]:
    return json.loads((COMPONENT_DIR / relative).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# en.json
# ---------------------------------------------------------------------------


def test_entity_keys_complete_with_names() -> None:
    en = _load_json("translations/en.json")
    entity = en["entity"]
    for platform, keys in ENTITY_KEYS.items():
        assert set(entity[platform]) == keys, platform
        for key in keys:
            name = entity[platform][key]["name"]
            assert isinstance(name, str) and name.strip(), (platform, key)


def test_service_translations_cover_all_fields() -> None:
    en = _load_json("translations/en.json")
    services = en["services"]
    assert set(services) == set(SERVICE_FIELDS)
    for service, fields in SERVICE_FIELDS.items():
        block = services[service]
        assert block["name"].strip(), service
        assert block["description"].strip(), service
        assert set(block["fields"]) == fields, service
        for field in fields:
            spec = block["fields"][field]
            assert spec["name"].strip(), (service, field)
            assert spec["description"].strip(), (service, field)


def test_services_yaml_structure_matches_translations() -> None:
    """services.yaml is structure-only; fields + required flags must agree."""
    en = _load_json("translations/en.json")
    services_yaml = yaml.safe_load((COMPONENT_DIR / "services.yaml").read_text())
    assert set(services_yaml) == set(en["services"])
    for service, block in services_yaml.items():
        assert set(block["fields"]) == set(en["services"][service]["fields"]), service
        required = {f for f, spec in block["fields"].items() if spec.get("required")}
        assert required == SERVICE_REQUIRED[service], service
        assert block["target"]["entity"]["integration"] == "bscpylgtv"
        assert block["target"]["entity"]["domain"] == "media_player"


def test_exception_translations_exactly_match() -> None:
    en = _load_json("translations/en.json")
    exceptions = en["exceptions"]
    assert set(exceptions) == EXCEPTION_KEYS
    for key, block in exceptions.items():
        assert block["message"].strip(), key
    # The removed v1 pairing timeout has no UI surface anymore.
    assert "pairing_timeout" not in exceptions


def test_v1_phantom_keys_absent() -> None:
    """oled_light / ai_picture_pro / reboot_soft must not resurface."""
    en = _load_json("translations/en.json")
    raw = json.dumps(en)
    for phantom in ("oled_light", "ai_picture_pro", "reboot_soft"):
        assert phantom not in raw, phantom


# ---------------------------------------------------------------------------
# icons.json
# ---------------------------------------------------------------------------


def test_icons_cover_services_and_button_entities() -> None:
    icons = _load_json("icons.json")
    assert set(icons["services"]) == set(SERVICE_FIELDS)
    for service, spec in icons["services"].items():
        assert spec["service"].startswith("mdi:"), service
    for platform, keys in ENTITY_KEYS.items():
        if platform not in icons["entity"]:
            continue  # platforms using HA's default icon
        for key in keys:
            icon = icons["entity"][platform][key]["default"]
            assert icon.startswith("mdi:"), (platform, key)


def test_button_entity_icons_present() -> None:
    icons = _load_json("icons.json")
    assert set(icons["entity"]["button"]) == ENTITY_KEYS["button"]


def test_no_attr_icon_in_sources() -> None:
    """Icon translations only — no hard-coded _attr_icon in entity code."""
    pattern = re.compile(r"_attr_icon\b")
    offenders = [
        str(path)
        for path in sorted(COMPONENT_DIR.rglob("*.py"))
        if "__pycache__" not in path.parts and pattern.search(path.read_text())
    ]
    assert offenders == []
