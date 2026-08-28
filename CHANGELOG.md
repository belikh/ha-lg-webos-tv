# Changelog

## 2.0.0

**Major release — breaking changes.** Read
[RELEASE_NOTES_v2.0.0.md](RELEASE_NOTES_v2.0.0.md) for the full migration
guide (entity/device migration, key-storage migration, removed entities and
services).

### Breaking changes

*   **Entity & device migration:** unique IDs now derive from the TV's
    `deviceUUID` instead of its IP address / config-entry id. Old v1 entities
    are orphaned; see the release notes for cleanup guidance.
*   **Key storage:** the pairing key moved from
    `.storage/bscpylgtv_<ip>.sqlite` into the config entry (legacy files are
    read once automatically, never deleted).
*   **Removed entities:** `oled_light` number (use `backlight` — same control
    on OLED panels), `reboot_soft` and `show_screen_saver` buttons (dead on
    modern webOS), `switch.ai_picture_pro` (phantom).
*   **Services:** `launch_app_with_params` merged into `launch_app` (new
    `params` field); `command` now takes a raw SSAP endpoint (e.g.
    `system.launcher/open`) instead of a library method name — **old
    automations using method names break**.
*   **`turn_on` is Wake-on-LAN only** (the SSAP `power_on` API is dead on
    modern webOS); requires the TV's MAC address (auto-detected, manual entry
    via options flow).

### Added

*   Supervised push connection: automatic reconnect, zombie-connection
    self-healing, watchdog probes.
*   Reauthentication and reconfigure flows; SSDP discovery updates a changed
    IP in place.
*   Options flow: source list filter + manual MAC address.
*   New entities: channel select, current channel sensor, `remote` with full
    button set + pointer + text input, screen-off/on buttons, `tpc` / `gsr`
    switches.
*   New services: `button`, `select_sound_output`, `take_screenshot` (returns
    base64 or writes a file).
*   `icons.json`, complete English translations including exceptions,
    redacted diagnostics, `quality_scale.yaml`, full test suite.

### Fixed

*   **Issue #9 — "Doesn't work after TV was off":** entities recover
    automatically when the TV returns (no more Home Assistant restart),
    reloading the integration works even with a wedged connection, and the
    sound output no longer snaps back to `tv_speaker` after an off/on cycle.
*   **Library teardown crash on Python 3.11+:** `bscpylgtv`'s connection
    teardown fed raw callback coroutines to `asyncio.wait`, which raises
    `TypeError` on Python 3.11+ — killing `disconnect()`, mid-unload, and the
    library's own power-off handling. v2 registers its state-update callback
    in a Task-returning form that is immune on every Python; the proper
    upstream fix is pending [chros73/bscpylgtv#8](https://github.com/chros73/bscpylgtv/pull/8).
*   State updates dying due to dict iteration over apps/inputs — thanks
    **@Xitee1** for PR #8.
*   Screenshot bytes are no longer discarded (response/file write).
*   Remote `VOLUMEUP`/`ENTER` key mapping (`input_button` TypeError).

### Credits

*   [chros73](https://github.com/chros73) for the `bscpylgtv` library.
*   The HA core `webostv` maintainers — architecture reference.
*   [@Xitee1](https://github.com/Xitee1) — PR #8 and issue #9.

## v1.0.4

### Changes

*   **Fix:** Added timeout to connection attempts during setup to prevent infinite hanging if pairing fails or is pending.

## v1.0.1

### Changes

*   **Unified Release:** Merged all features from development branches into a stable release.
*   **Cleanup:** Consolidated code base and removed obsolete development branches.

## v1.0.0

### New Features

*   **Initial Release:** Fully fledged Home Assistant integration for LG WebOS TVs using `bscpylgtv`.
*   **Media Player:** Complete control (Power, Volume, Source, Playback) + `play_media` app launching.
*   **Remote:** Full remote control support (Keys, Cursor).
*   **Notify:** Toast notification support.
*   **Configuration:**
    *   UI-based Config Flow with SSDP Auto-discovery.
    *   **Unique ID:** Uses device UUID for persistent registry tracking.
*   **Entities:**
    *   **Buttons:** Screen Off/On, Screensaver, Screenshot.
    *   **Advanced Buttons (Disabled by Default):** Reboot, Soft Reboot, TPC/GSR Control.
    *   **Numbers (Disabled by Default):** Picture Settings (Backlight, Contrast, Brightness, Color, Sharpness, OLED Light).
    *   **Selects:** Picture Mode, Sound Output.
    *   **Sensors:** Current App, Volume, Power State, System Info.
*   **Services:** `launch_app`, `launch_app_with_params`, `command`, `set_settings`.
*   **HACS Support:** Ready for easy installation.
