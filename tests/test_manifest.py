"""Tests for manifest.json metadata (plan AC-1/AC-2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "bscpylgtv"
    / "manifest.json"
)

MANIFEST: dict[str, Any] = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def test_domain_and_version() -> None:
    assert MANIFEST["domain"] == "bscpylgtv"
    assert MANIFEST["version"] == "2.0.0"
    assert MANIFEST["name"] == "LG WebOS TV (bscpylgtv)"


def test_requirements_pin_library() -> None:
    assert MANIFEST["requirements"] == ["bscpylgtv==0.5.3"]


def test_ownership_and_docs_urls() -> None:
    assert MANIFEST["codeowners"] == ["@belikh"]
    assert MANIFEST["documentation"].startswith(
        "https://github.com/belikh/ha-lg-webos-tv"
    )
    assert MANIFEST["issue_tracker"].startswith(
        "https://github.com/belikh/ha-lg-webos-tv"
    )


def test_integration_character() -> None:
    assert MANIFEST["integration_type"] == "device"
    assert MANIFEST["iot_class"] == "local_push"
    assert MANIFEST["config_flow"] is True
    assert MANIFEST["quality_scale"] == "gold"
    assert MANIFEST["loggers"] == ["bscpylgtv"]


def test_dependencies_and_ssdp() -> None:
    assert "ssdp" in MANIFEST["dependencies"]
    assert MANIFEST["ssdp"] == [{"st": "urn:lge-com:service:webos-second-screen:1"}]
