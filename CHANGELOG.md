# Changelog

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
