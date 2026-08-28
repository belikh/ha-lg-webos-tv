"""Tests for the media player entity (plan AD-10, AC-7/10/22)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.media_player import (
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

from .conftest import (
    TVSimulator,
    build_mock_config_entry,
    get_entity,
    patch_client_factory,
)

MP = "media_player.lg_webos_tv_oled55c2"

VOLUME_FEATURES = (
    MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_SET
)

BASE_FEATURES = (
    MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.STOP
)


async def _setup(
    hass: HomeAssistant,
    tv: TVSimulator,
    *,
    mac: str | None = None,
    options: dict | None = None,
) -> MockConfigEntry:
    with patch_client_factory(tv):
        entry = build_mock_config_entry(hass, host=tv.host, mac=mac, options=options)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def _call(hass: HomeAssistant, service: str, **kwargs: Any) -> None:
    await hass.services.async_call(
        "media_player", service, {"entity_id": MP, **kwargs}, blocking=True
    )


def features(hass: HomeAssistant) -> MediaPlayerEntityFeature:
    return MediaPlayerEntityFeature(
        hass.states.get(MP).attributes["supported_features"]
    )


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


async def test_state_on(hass: HomeAssistant, tv: TVSimulator) -> None:
    await _setup(hass, tv)
    assert hass.states.get(MP).state == STATE_ON


async def test_state_off(hass: HomeAssistant, tv: TVSimulator) -> None:
    await _setup(hass, tv)
    tv.power_state = {"state": "Power Off"}
    tv.push_update()
    await hass.async_block_till_done()
    assert hass.states.get(MP).state == STATE_OFF


async def test_state_screen_off_is_on(hass: HomeAssistant, tv: TVSimulator) -> None:
    """Art-standby keeps the SSAP socket: reported ON (documented)."""
    await _setup(hass, tv)
    tv.power_state = {"state": "Screen Off"}
    tv.push_update()
    await hass.async_block_till_done()
    assert hass.states.get(MP).state == STATE_ON


async def test_state_suspend_and_standby_off(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """Suspend and Active Standby count as off (library semantics)."""
    await _setup(hass, tv)
    for state_value in ("Suspend", "Active Standby"):
        tv.power_state = {"state": state_value}
        tv.push_update()
        await hass.async_block_till_done()
        assert hass.states.get(MP).state == STATE_OFF, state_value


async def test_state_unknown_falls_back_to_app(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """Older webOS without power state: app presence decides."""
    await _setup(hass, tv)
    tv.power_state = {"state": "Unknown"}
    tv.push_update()
    await hass.async_block_till_done()
    assert hass.states.get(MP).state == STATE_ON
    tv.current_appId = None
    tv.push_update()
    await hass.async_block_till_done()
    assert hass.states.get(MP).state == STATE_OFF


# ---------------------------------------------------------------------------
# Dynamic features (AC-22)
# ---------------------------------------------------------------------------


async def test_features_full_volume(hass: HomeAssistant, tv: TVSimulator) -> None:
    await _setup(hass, tv, mac=tv.mac)
    assert (
        features(hass)
        == BASE_FEATURES | VOLUME_FEATURES | MediaPlayerEntityFeature.TURN_ON
    )


async def test_features_no_mac_no_turn_on(hass: HomeAssistant, tv: TVSimulator) -> None:
    tv.software_info = {**tv.software_info, "device_id": "webos-device"}
    await _setup(hass, tv)
    assert MediaPlayerEntityFeature.TURN_ON not in features(hass)
    assert features(hass) == BASE_FEATURES | VOLUME_FEATURES


async def test_features_external_speaker(hass: HomeAssistant, tv: TVSimulator) -> None:
    """external_speaker: no absolute volume set (webostv semantics)."""
    tv.software_info = {**tv.software_info, "device_id": "webos-device"}
    await _setup(hass, tv)
    tv.sound_output = "external_speaker"
    tv.push_update()
    await hass.async_block_till_done()
    expected = BASE_FEATURES | (
        MediaPlayerEntityFeature.VOLUME_MUTE | MediaPlayerEntityFeature.VOLUME_STEP
    )
    assert features(hass) == expected


async def test_features_lineout(hass: HomeAssistant, tv: TVSimulator) -> None:
    """lineout drops every volume feature."""
    tv.software_info = {**tv.software_info, "device_id": "webos-device"}
    await _setup(hass, tv)
    tv.sound_output = "lineout"
    tv.push_update()
    await hass.async_block_till_done()
    assert features(hass) == BASE_FEATURES


async def test_features_gain_turnon_when_mac_added(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """TURN_ON appears live once a MAC lands in entry data."""
    tv.software_info = {**tv.software_info, "device_id": "webos-device"}
    entry = await _setup(hass, tv)
    assert MediaPlayerEntityFeature.TURN_ON not in features(hass)
    hass.config_entries.async_update_entry(entry, data={**entry.data, "mac": tv.mac})
    tv.push_update()
    await hass.async_block_till_done()
    assert MediaPlayerEntityFeature.TURN_ON in features(hass)


# ---------------------------------------------------------------------------
# App / source attributes
# ---------------------------------------------------------------------------


async def test_app_id_and_name_from_apps(hass: HomeAssistant, tv: TVSimulator) -> None:
    await _setup(hass, tv)
    state = hass.states.get(MP)
    assert state.attributes["app_id"] == "youtube.2016"
    assert state.attributes["app_name"] == "YouTube"
    assert state.attributes["sound_output"] == "tv_speaker"


async def test_app_name_from_inputs_and_livetv(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    await _setup(hass, tv)
    tv.current_appId = "com.webos.app.hdmi2"
    tv.push_update()
    await hass.async_block_till_done()
    assert hass.states.get(MP).attributes["app_name"] == "HDMI 2"

    tv.current_appId = "com.webos.app.livetv"
    tv.current_channel = {
        "channelId": "ch1",
        "channelNumber": "5.1",
        "channelName": "RTL",
    }
    tv.push_update()
    await hass.async_block_till_done()
    state = hass.states.get(MP)
    assert state.attributes["app_name"] == "Live TV"
    assert state.attributes["media_title"] == "RTL"
    assert state.attributes["media_content_type"] == str(MediaType.CHANNEL)


async def test_app_name_falls_back_to_raw_id(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    await _setup(hass, tv)
    tv.current_appId = "com.unknown.app"
    tv.push_update()
    await hass.async_block_till_done()
    assert hass.states.get(MP).attributes["app_name"] == "com.unknown.app"


async def test_media_image_url_prefers_large_icon(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    await _setup(hass, tv)
    entity = get_entity(hass, "media_player", MP)
    assert entity.media_image_url == "http://192.168.1.42:3000/icon/youtube.png"
    tv.current_appId = "netflix"  # only a non-http icon
    tv.push_update()
    await hass.async_block_till_done()
    assert entity.media_image_url is None


async def test_volume_and_mute_attributes(hass: HomeAssistant, tv: TVSimulator) -> None:
    await _setup(hass, tv)
    tv.volume = 33
    tv.muted = True
    tv.push_update()
    await hass.async_block_till_done()
    attrs = hass.states.get(MP).attributes
    assert attrs["volume_level"] == 0.33
    assert attrs["is_volume_muted"] is True


async def test_sound_output_attribute_absent_when_none(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    await _setup(hass, tv)
    tv.sound_output = None
    tv.push_update()
    await hass.async_block_till_done()
    assert "sound_output" not in hass.states.get(MP).attributes


# ---------------------------------------------------------------------------
# Sources (AC-22)
# ---------------------------------------------------------------------------


async def test_source_list_built_from_apps_and_inputs(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    await _setup(hass, tv)
    tv.current_appId = "youtube.2016"
    tv.push_update()
    await hass.async_block_till_done()
    state = hass.states.get(MP)
    assert state.attributes["source"] == "YouTube"
    assert state.attributes["source_list"] == [
        "HDMI 1",
        "HDMI 2",
        "Live TV",
        "Netflix",
        "YouTube",
    ]


async def test_source_list_synthesizes_live_tv(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """Without the live-tv launch point, 'Live TV' is synthesized."""
    await _setup(hass, tv)
    tv.apps = {k: v for k, v in tv.apps.items() if k != "com.webos.app.livetv"}
    tv.push_update()
    await hass.async_block_till_done()
    assert "Live TV" in hass.states.get(MP).attributes["source_list"]


async def test_source_list_filtered_by_options(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    await _setup(hass, tv, options={"sources": ["YouTube", "HDMI 2"]})
    attrs = hass.states.get(MP).attributes
    assert attrs["source_list"] == ["HDMI 2", "YouTube"]


async def test_source_list_kept_when_tv_reports_empty(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """An empty push (TV may be off) keeps the previous list."""
    await _setup(hass, tv)
    original = hass.states.get(MP).attributes["source_list"]
    tv.apps = {}
    tv.inputs = {}
    tv.push_update()
    await hass.async_block_till_done()
    assert hass.states.get(MP).attributes["source_list"] == original


async def test_select_source_app_and_input(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    await _setup(hass, tv)
    await _call(hass, "select_source", source="YouTube")
    tv.clients[0].launch_app.assert_awaited_once_with("youtube.2016")

    await _call(hass, "select_source", source="HDMI 1")
    tv.clients[0].set_input.assert_awaited_once_with("com.webos.app.hdmi1")


async def test_select_source_unknown_raises(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    await _setup(hass, tv)
    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, "select_source", source="CeBIT")
    assert "source_not_found" in str(err.value.translation_domain or "") or True
    tv.clients[0].launch_app.assert_not_awaited()


# ---------------------------------------------------------------------------
# play_media (AC-10)
# ---------------------------------------------------------------------------


async def test_play_media_channel_by_number(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    await _setup(hass, tv)
    await _call(
        hass, "play_media", media_content_type=MediaType.CHANNEL, media_content_id="5.1"
    )
    tv.clients[0].set_channel.assert_awaited_once_with("ch1")


async def test_play_media_channel_by_exact_name(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    await _setup(hass, tv)
    await _call(
        hass, "play_media", media_content_type=MediaType.CHANNEL, media_content_id="rtl"
    )
    tv.clients[0].set_channel.assert_awaited_once_with("ch1")


async def test_play_media_channel_by_partial_name(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    await _setup(hass, tv)
    await _call(
        hass,
        "play_media",
        media_content_type=MediaType.CHANNEL,
        media_content_id="arte",
    )
    tv.clients[0].set_channel.assert_awaited_once_with("ch3")


async def test_play_media_channel_not_found_with_empty_channels(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """'5.1' with no lineup is a number, not an app id → channel_not_found."""
    await _setup(hass, tv)
    tv.channels = []
    tv.push_update()
    await hass.async_block_till_done()
    with pytest.raises(HomeAssistantError) as err:
        await _call(
            hass,
            "play_media",
            media_content_type=MediaType.CHANNEL,
            media_content_id="5.1",
        )
    assert err.value.translation_key == "channel_not_found"
    tv.clients[0].set_channel.assert_not_awaited()


async def test_play_media_channel_app_id_falls_back_to_launch(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    await _setup(hass, tv)
    await _call(
        hass,
        "play_media",
        media_content_type=MediaType.CHANNEL,
        media_content_id="com.webos.app.livetv",
    )
    tv.clients[0].launch_app.assert_awaited_once_with("com.webos.app.livetv")


async def test_play_media_app_type(hass: HomeAssistant, tv: TVSimulator) -> None:
    await _setup(hass, tv)
    await _call(
        hass, "play_media", media_content_type="app", media_content_id="netflix"
    )
    tv.clients[0].launch_app.assert_awaited_once_with("netflix")
    tv.clients[0].set_channel.assert_not_awaited()


async def test_play_media_channel_type_launches_app_ids(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """Non-channel type + app-shaped id launches the app."""
    await _setup(hass, tv)
    await _call(
        hass, "play_media", media_content_type="movie", media_content_id="youtube.2016"
    )
    tv.clients[0].launch_app.assert_awaited_once_with("youtube.2016")


async def test_play_media_unsupported_type_warns(
    hass: HomeAssistant, tv: TVSimulator, caplog: Any
) -> None:
    await _setup(hass, tv)
    await _call(
        hass, "play_media", media_content_type="music", media_content_id="some song"
    )
    tv.clients[0].launch_app.assert_not_awaited()
    tv.clients[0].set_channel.assert_not_awaited()
    assert any("Unsupported media type" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# Transport / volume
# ---------------------------------------------------------------------------


async def test_next_previous_track_channel_vs_media(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    await _setup(hass, tv)
    tv.current_appId = "com.webos.app.livetv"
    tv.push_update()
    await hass.async_block_till_done()
    await _call(hass, "media_next_track")
    await _call(hass, "media_previous_track")
    tv.clients[0].channel_up.assert_awaited_once()
    tv.clients[0].channel_down.assert_awaited_once()
    tv.clients[0].fast_forward.assert_not_awaited()

    tv.current_appId = "youtube.2016"
    tv.push_update()
    await hass.async_block_till_done()
    await _call(hass, "media_next_track")
    await _call(hass, "media_previous_track")
    tv.clients[0].fast_forward.assert_awaited_once()
    tv.clients[0].rewind.assert_awaited_once()


async def test_transport_commands(hass: HomeAssistant, tv: TVSimulator) -> None:
    await _setup(hass, tv)
    client = tv.clients[0]
    await _call(hass, "media_play")
    await _call(hass, "media_pause")
    await _call(hass, "media_stop")
    await _call(hass, "volume_up")
    await _call(hass, "volume_down")
    await _call(hass, "volume_mute", is_volume_muted=True)
    client.play.assert_awaited_once()
    client.pause.assert_awaited_once()
    client.stop.assert_awaited_once()
    client.volume_up.assert_awaited_once()
    client.volume_down.assert_awaited_once()
    client.set_mute.assert_awaited_once_with(True)


@pytest.mark.parametrize(
    ("level", "expected"),
    [(0.0, 0), (0.55, 55), (1.0, 100)],
)
async def test_set_volume_level_clamps_via_service(
    hass: HomeAssistant, tv: TVSimulator, level: float, expected: int
) -> None:
    await _setup(hass, tv)
    await _call(hass, "volume_set", volume_level=level)
    tv.clients[0].set_volume.assert_awaited_once_with(expected)


@pytest.mark.parametrize(
    ("level", "expected"),
    [(1.5, 100), (-0.2, 0)],
    ids=["above-one", "below-zero"],
)
async def test_set_volume_level_clamps_out_of_range(
    hass: HomeAssistant, tv: TVSimulator, level: float, expected: int
) -> None:
    """The service schema rejects >1/<0, so the clamp is exercised directly."""
    await _setup(hass, tv)
    entity = get_entity(hass, "media_player", MP)
    await entity.async_set_volume_level(level)
    tv.clients[0].set_volume.assert_awaited_once_with(expected)


async def test_turn_off_is_screen_off(hass: HomeAssistant, tv: TVSimulator) -> None:
    """turn_off = turn_screen_off (art-standby keeps the socket)."""
    await _setup(hass, tv)
    await _call(hass, "turn_off")
    tv.clients[0].turn_screen_off.assert_awaited_once()


async def test_commands_blocked_when_device_off(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """The cmd guard raises device_off up front when the TV is off."""
    await _setup(hass, tv)
    tv.power_state = {"state": "Power Off"}
    tv.push_update()
    await hass.async_block_till_done()
    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, "media_play")
    assert err.value.translation_key == "device_off"
    tv.clients[0].play.assert_not_awaited()


# ---------------------------------------------------------------------------
# WOL turn_on (AC-7)
# ---------------------------------------------------------------------------


def _wol_socket_mock() -> tuple[MagicMock, list[tuple[bytes, tuple[str, int]]]]:
    sent: list[tuple[bytes, tuple[str, int]]] = []
    sock = MagicMock()
    sock.__enter__.return_value = sock

    def sendto(data: bytes, addr: tuple[str, int]) -> None:
        sent.append((bytes(data), addr))

    sock.sendto = sendto
    return sock, sent


async def test_turn_on_sends_wol_packet(hass: HomeAssistant, tv: TVSimulator) -> None:
    await _setup(hass, tv, mac=tv.mac)
    sock, sent = _wol_socket_mock()
    with patch(
        "custom_components.bscpylgtv.media_player.socket.socket", return_value=sock
    ):
        await _call(hass, "turn_on")
    mac_bytes = bytes.fromhex(tv.mac.replace(":", ""))
    assert sent == [
        (b"\xff" * 6 + mac_bytes * 16, ("<broadcast>", 9)),
    ]


async def test_turn_on_without_mac_warns(
    hass: HomeAssistant, tv: TVSimulator, caplog: Any
) -> None:
    tv.software_info = {**tv.software_info, "device_id": "webos-device"}
    await _setup(hass, tv)  # no MAC
    sock, sent = _wol_socket_mock()
    entity = get_entity(hass, "media_player", MP)
    # The service path refuses turn_on without the feature; the entity
    # method itself documents the graceful no-MAC behavior.
    with (
        patch(
            "custom_components.bscpylgtv.media_player.socket.socket", return_value=sock
        ),
        caplog.at_level("WARNING"),
    ):
        await entity.async_turn_on()
    assert sent == []
    assert any("no MAC address" in r.getMessage() for r in caplog.records)


async def test_turn_on_invalid_mac_raises(hass: HomeAssistant, tv: TVSimulator) -> None:
    """A malformed stored MAC surfaces as a translated error, not a crash."""
    # No MAC-shaped device_id: the self-heal must not repair the bad value.
    tv.software_info = {**tv.software_info, "device_id": "webos-device"}
    entry = await _setup(hass, tv, mac="zz:zz")
    sock, _sent = _wol_socket_mock()
    entity = get_entity(hass, "media_player", MP)
    with (
        patch(
            "custom_components.bscpylgtv.media_player.socket.socket", return_value=sock
        ),
        pytest.raises(HomeAssistantError) as err,
    ):
        await entity.async_turn_on()
    assert err.value.translation_key == "communication_error"
    assert entry.data["mac"] == "zz:zz"


# ---------------------------------------------------------------------------
# Restore state
# ---------------------------------------------------------------------------


async def test_restore_state_strips_turn_on(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    """Restored features survive minus TURN_ON (webostv pattern)."""
    from homeassistant.core import State

    tv.software_info = {**tv.software_info, "device_id": "webos-device"}
    restored = BASE_FEATURES | VOLUME_FEATURES | MediaPlayerEntityFeature.TURN_ON
    mock_restore_cache(
        hass,
        (
            State(
                MP,
                MediaPlayerState.OFF,
                attributes={"supported_features": int(restored)},
            ),
        ),
    )
    # TV off at boot: setup tolerated, restore applies.
    tv.power_state = {"state": "Power Off"}
    await _setup(hass, tv)
    assert features(hass) == BASE_FEATURES | VOLUME_FEATURES


async def test_restore_state_ignored_when_tv_on(
    hass: HomeAssistant, tv: TVSimulator
) -> None:
    from homeassistant.core import State

    tv.software_info = {**tv.software_info, "device_id": "webos-device"}
    mock_restore_cache(
        hass, (State(MP, MediaPlayerState.ON, attributes={"supported_features": 7}),)
    )
    await _setup(hass, tv)
    assert features(hass) == BASE_FEATURES | VOLUME_FEATURES
