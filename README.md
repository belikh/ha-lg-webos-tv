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
*   **Remote:**
    *   Full remote control support (Up, Down, Left, Right, Select, Back, Home, Menu, etc.).
*   **Notify:**
    *   Send toast notifications to the TV screen.
*   **Entities:**
    *   **Buttons:**
        *   Standard: Turn Screen Off/On, Screensaver, Screenshot.
        *   *Advanced (Disabled by default):* Reboot, Soft Reboot, TPC/GSR toggles (OLED protection).
    *   **Numbers:**
        *   *Advanced (Disabled by default):* Backlight, Contrast, Brightness, Color, Sharpness, OLED Light.
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

## Entities & Options

### Dangerous/Advanced Options
Some entities are **disabled by default** to prevent accidental changes that could affect picture quality or device stability. To enable them:
1.  Go to the Device page for your TV in Home Assistant.
2.  Click on "Entities" or the specific disabled entity.
3.  Click the "Settings" (gear) icon.
4.  Toggle "Enabled" and update.

**Disabled Entities:**
*   **Reboot / Soft Reboot:** Restarts the TV.
*   **TPC / GSR:** Temporal Peak Luminance Control and Global Sticky Reduction. These are OLED protection mechanisms. Disabling them might void warranties or cause burn-in. Use with caution.
*   **Picture Settings (Numbers):** Direct control over Backlight, Contrast, etc.

## Services

### `media_player.play_media`
You can launch apps using standard media player calls:
```yaml
service: media_player.play_media
target:
  entity_id: media_player.lg_webos_tv
data:
  media_content_type: app
  media_content_id: com.webos.app.youtube
```

### `bscpylgtv.command`
Send raw commands to the library.
```yaml
service: bscpylgtv.command
target:
  entity_id: media_player.lg_webos_tv
data:
  command: system_info
```

### `notify.notify`
Send a toast notification.
```yaml
service: notify.lg_webos_tv_notify
data:
  message: "Hello World!"
```

## Credits

*   Based on the [`bscpylgtv`](https://github.com/chros73/bscpylgtv) library by chros73.
