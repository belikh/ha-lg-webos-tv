---
title: Entities
summary: Every entity the integration creates, with its platform, category, default state and range.
order: 10
audience: users
status: draft
---

Each TV becomes one device. Entities marked disabled are created disabled and you enable them on the entity settings page.

| Platform | Entity | Category | Default | Description |
| --- | --- | --- | --- | --- |
| `media_player` | LG WebOS TV (named after the device) | none | enabled | Power, volume, mute, source (apps and inputs), play, pause, stop, next, previous and `play_media` for apps and channels. |
| `remote` | Remote | none | enabled | Library buttons plus pointer (`MOVE`, `CLICK`, `SCROLL`) and text (`TEXT`) commands. |
| `notify` | Notifications | none | enabled | Toast message on the TV screen. |
| `button` | Turn screen off | none | enabled | Switches the panel off and keeps the TV running. |
| `button` | Turn screen on | none | enabled | Switches the panel back on. |
| `button` | Reboot | config | disabled | Reboots the TV. |
| `number` | Backlight | config | disabled | Backlight or OLED light, 0 to 100. |
| `number` | Contrast | config | disabled | 0 to 100. |
| `number` | Brightness | config | disabled | 0 to 100. |
| `number` | Color | config | disabled | Color saturation, 0 to 100. |
| `number` | Sharpness | config | disabled | 0 to 50. |
| `number` | Color temperature | config | disabled | -50 to +50. |
| `select` | Picture mode | none | enabled | Live-read mode list, with a fixed fallback list if the TV refuses the read. |
| `select` | Sound output | none | enabled | Output list in [[reference/sound-outputs]]. |
| `select` | Channel | none | enabled | Channel list. Appears after you open Live TV once. |
| `sensor` | Current app | none | enabled | Name of the running app. |
| `sensor` | Volume | none | enabled | Volume in %. |
| `sensor` | Power state | none | enabled | `Active`, `Active Standby`, `Screen Off`, `Suspend` and other TV states. |
| `sensor` | Current channel | diagnostic | enabled | Channel number and name while Live TV runs. |
| `switch` | TPC | config | disabled | Temporal Peak Luminance Control, OLED burn-in protection. |
| `switch` | GSR | config | disabled | Global Sticky Reduction, OLED burn-in protection. |

:::warning Burn-in protection
TPC and GSR are OLED panel-protection settings. Turning them off can raise the risk of burn-in.
:::

## Media player behavior

- Supported features: turn off, pause, play, stop, next, previous, select source and play media. Turn on appears when a MAC address is stored.
- Volume features depend on the sound output. `tv_speaker` and `headphone` support absolute volume. External outputs support step and mute only. See [[concepts/sound-outputs]].
- The `sound_output` attribute carries the current output.
- `turn_off` does nothing when the TV is already off or disconnected, so automations do not fail.
- The state restores after a restart while the TV is off.

## Remote behavior

The remote reports on while the TV is in `Screen Off`, because the websocket stays open and the remote can wake the screen. Its current activity is the title of the current input or app. Commands are in [[reference/remote-commands]].

## Notify behavior

A webOS toast is one line, so a title is prefixed to the message as `<title>: <message>`.

The notify entity can attach an `icon` file path. Home Assistant currently passes only `message` and `title` to notify entities, so the icon is reachable only from direct entity calls. The path must be inside an allowed directory.

```yaml title="Show a toast"
service: notify.send_message
target:
  entity_id: notify.lg_webos_tv_notifications
data:
  message: "Dinner is ready!"
```

:::see-also
- [[reference/services]]
- [[reference/options]]
:::
