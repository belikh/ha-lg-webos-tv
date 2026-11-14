---
title: Services
summary: The six bscpylgtv services with their fields, plus the standard services the TV supports.
order: 20
audience: users
status: draft
---

All services target the `media_player` entity of the TV. Developer tools in Home Assistant show the same names and descriptions.

| Service | Fields | Purpose |
| --- | --- | --- |
| `bscpylgtv.button` | `button` (required) | Press a remote button. |
| `bscpylgtv.command` | `command` (required), `payload` | Send a raw [[term:SSAP]] endpoint. |
| `bscpylgtv.select_sound_output` | `sound_output` (required) | Change the sound output. |
| `bscpylgtv.launch_app` | `app_id` (required), `params` | Launch an app. |
| `bscpylgtv.take_screenshot` | `filename` | Capture the screen. |
| `bscpylgtv.set_settings` | `category` (required), `settings` (required) | Write TV settings. |

## bscpylgtv.button

```yaml title="Press INFO"
service: bscpylgtv.button
target:
  entity_id: media_player.lg_webos_tv
data:
  button: INFO
```

Button names are in [[reference/remote-commands]]. An unknown name fails with `Unknown button <name>.`

## bscpylgtv.command

Sends a raw SSAP endpoint. The response comes back when you call the service with a response variable. This is for expert use.

```yaml title="Open a URL"
service: bscpylgtv.command
target:
  entity_id: media_player.lg_webos_tv
data:
  command: system.launcher/open
  payload:
    target: https://www.youtube.com
```

The service cannot read return values of Luna-only endpoints (library limitation).

## bscpylgtv.select_sound_output

```yaml title="Select HDMI ARC"
service: bscpylgtv.select_sound_output
target:
  entity_id: media_player.lg_webos_tv
data:
  sound_output: external_arc
```

Values are in [[reference/sound-outputs]].

## bscpylgtv.launch_app

```yaml title="Open a YouTube video"
service: bscpylgtv.launch_app
target:
  entity_id: media_player.lg_webos_tv
data:
  app_id: com.webos.app.youtube
  params:
    contentTarget: https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

## bscpylgtv.take_screenshot

Without `filename` the JPEG returns as base64 in the response. With `filename` the integration writes the file. Path rules and the warning about `www` are in [[guides/take-screenshot]].

```yaml title="Write a file"
service: bscpylgtv.take_screenshot
target:
  entity_id: media_player.lg_webos_tv
data:
  filename: /media/tv_screen.jpg
```

## bscpylgtv.set_settings

Writes settings through the settings API of the TV.

```yaml title="Set backlight and contrast"
service: bscpylgtv.set_settings
target:
  entity_id: media_player.lg_webos_tv
data:
  category: picture
  settings:
    backlight: 55
    contrast: 80
```

## Standard services

| Service | Use |
| --- | --- |
| `media_player.play_media` with `app` or `channel` | See [[guides/launch-apps-and-channels]]. |
| `media_player.select_source` | Pick an app or input from the source list. |
| `media_player.turn_on`, `turn_off`, `volume_*`, `media_*` | The usual media player controls. |
| `notify.send_message` | Toast on the TV. See [[reference/entities]]. |
| `remote.send_command` | See [[reference/remote-commands]]. |

:::see-also
- [[reference/entities]]
- [[guides/take-screenshot]]
:::
