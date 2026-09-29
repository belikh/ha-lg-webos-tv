# Changelog

## 2.0.3

### Fixed

*   **webOS 26 sets (firmware 43.x) — pairing and reconnection.** LG
    blacklists the certificate in the legacy signed registration manifest
    (`403 Pairing rejected: blacklisted certificate detected`) and
    invalidates existing pairing keys on these sets, while `bscpylgtv` still
    sends that manifest. The integration now keeps the signed manifest (and
    the elevated permissions only it grants — `WRITE_SETTINGS` powers the
    picture-setting controls) but detects the rejection — a
    `PyLGTVPairException` while pairing, or a dead link right after a
    stored-key connect — and retries once with the merged unsigned
    manifest. This mirrors the recovery `aiowebostv` shipped for Home
    Assistant core 2026.8.3. A transport failure (TV off or unreachable)
    does **not** trigger the retry, so an unreachable TV still costs a
    single connect timeout. When the TV invalidated the old key, the
    reauthentication flow re-pairs with the same fallback.

## 2.0.2

### Fixed

*   **Pairing on webOS 25 sets (LG C3/C5 and similar).** These TVs never
    answer the library's `hello` handshake, so every connect that requested
    it — pairing and runtime alike — blocked until the caller's timeout and
    the TV never showed a pairing prompt (issue #11). The integration no
    longer requests hello during pairing or normal operation. The device
    UUID is recovered afterwards with a bounded, silent probe on the
    already-registered connection; TVs that ignore hello fall back to the
    MAC address from software info, and to the host as a last resort.
*   **Duplicate entities after a v1 → v2 upgrade.** The lazy unique-id
    migration changed the config-entry id but left the existing entity
    registry entries under their old IP-shaped ids, so the next setup
    registered a second set of entities alongside the old ones (the
    duplicate/triple entities reported after upgrading). Entity registry
    ids derived from the entry id are now rewritten in place during the
    migration, keeping entity ids and history intact.

### Changed

*   **`bscpylgtv` 0.5.4** (was 0.5.3): picks up the upstream teardown
    closeout fix for Python 3.11+. The state-update callback registration
    is aligned with it (a plain coroutine function; the library now wraps
    callback results itself).

## 2.0.1

### Fixed

*   **Screenshots on current webOS sets.** webOS 04.40.16 (verified on a CX
    OLED48CXPTA) returns no `image` key — only an `imageUri` pointing at a
    self-signed `https://` resource on the TV, which crashed the screenshot
    button with a raw `KeyError`. The shared implementation now handles all
    payload shapes (base64 `image`, `imageUri` URL, `imageUri` data-URI)
    and reports write failures properly.
*   **Picture mode select now remembers its last written value** across HA
    restarts. Some models (verified on a CX OLED48CXPTA, webOS 04.40.16)
    refuse every read of the current picture mode, so the select showed
    `unknown` after every restart even after being set from HA. The value
    is now restored via `RestoreEntity`. After updating, set the mode once
    from HA and it persists.
*   **Sharpness / color temperature sliders remember their last written
    value** for models that reject reads of those keys (same restore
    treatment); the four TV-pushed sliders are unaffected.

### Documented

*   Troubleshooting entries: picture-mode `unknown` state and sharpness /
    color temperature `unknown` state (firmware read restrictions), and the
    empty channel select (no tuner channels scanned on the TV).

### Verified against a real TV (OLED48CXPTA, webOS 04.40.16)

*   Full function audit: every library call site re-checked against the
    `bscpylgtv` 0.5.3 source and live-probed — volume/mute get+set,
    sound-output get+change, toast notifications, screenshot capture,
    picture-settings push shapes, channel-less behaviour. Writes verified
    as same-value no-ops where a change would have been visible.

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
