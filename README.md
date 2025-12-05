# LG WebOS TV (bscpylgtv) Home Assistant Integration

This is a custom component for Home Assistant that provides a fully-fledged integration for LG WebOS TVs using the [`bscpylgtv`](https://github.com/chros73/bscpylgtv) library.

It is designed to "expose everything" possible from the library, including advanced calibration features, system settings, and comprehensive control.

## Features

*   **Config Flow:** Easy setup via the UI with auto-discovery (SSDP) and pairing guidance.
*   **Media Player:**
    *   Power (On/Off), Volume, Mute.
    *   Source selection (Inputs and Apps).
    *   Play/Pause/Stop/Next/Previous.
    *   `play_media` support for launching apps.
*   **Entities:**
    *   **Buttons:** Reboot, Soft Reboot, Screen Off/On, Screensaver, Screenshot, TPC/GSR toggles.
    *   **Numbers:** Backlight, Contrast, Brightness, Color, Sharpness, OLED Light.
    *   **Selects:** Picture Mode, Sound Output.
    *   **Sensors:** Current App, Volume, Power State, Software Info (Model, Version, Device ID).
    *   **Switches:** AI Picture Pro (experimental).
*   **Services:**
    *   `launch_app`: Launch an app by ID.
    *   `launch_app_with_params`: Launch an app with JSON parameters.
    *   `command`: Execute any method available in the `WebOsClient` library.
    *   `set_settings`: Update system or picture settings.

## Installation

### HACS (Recommended)

1.  Open HACS in Home Assistant.
2.  Go to "Integrations".
3.  Click the 3 dots in the top right corner and select "Custom repositories".
4.  Add the URL of this repository.
5.  Select "Integration" as the category.
6.  Click "Add".
7.  Find "LG WebOS TV (bscpylgtv)" in the list and install it.
8.  Restart Home Assistant.

### Manual Installation

1.  Download the `custom_components/bscpylgtv` folder from this repository.
2.  Copy it to your Home Assistant `custom_components` directory.
3.  Restart Home Assistant.

## Configuration

1.  Go to **Settings** > **Devices & Services**.
2.  Click **Add Integration**.
3.  Search for **LG WebOS TV (bscpylgtv)**.
4.  Enter the IP address of your TV.
5.  Follow the instructions to pair (accept the prompt on your TV).

## Credits

*   Based on the [`bscpylgtv`](https://github.com/chros73/bscpylgtv) library by chros73.
