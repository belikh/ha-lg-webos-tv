# LG WebOS TV (bscpylgtv) for Home Assistant

<!-- TODO: screenshots — add device dashboard and entity screenshots here -->

A custom integration for controlling **LG TVs running webOS** in Home Assistant,
built on the [`bscpylgtv`](https://github.com/chros73/bscpylgtv) library by
[chros73](https://github.com/chros73).

The integration keeps a persistent websocket connection to the TV and receives
state updates as they happen (push, not polling). Its architecture closely
follows the built-in Home Assistant `webostv` integration — thanks to the HA
core webostv maintainers for the reference implementation — while exposing the
additional surface the `bscpylgtv` library offers: picture calibration sliders,
picture mode / sound output / channel selects, power-state and channel sensors,
a full remote with pointer and text input, screen notifications, and raw SSAP
access for power users.

## Features

- **Setup via UI** with SSDP auto-discovery and TV-prompt pairing (no PIN codes).
- **Push updates** over a supervised websocket connection with automatic
  reconnect and self-healing after TV restarts or network hiccups.
- **Turn TV on** via Wake-on-LAN (MAC address auto-detected).
- **Reauth & reconfigure flows** for pairing-key loss and IP/host changes.
- **Diagnostics** with sensitive data redacted.
- Entities across media player, remote, notify, button, number, select, sensor
  and switch platforms (see the table below).
- Six integration services for advanced control, including raw SSAP commands
  and screenshots.

## Installation

### HACS (recommended)

1. Open **HACS** in Home Assistant and go to **Integrations**.
2. Click the three dots (top right) → **Custom repositories**.
3. Add `https://github.com/belikh/ha-lg-webos-tv` with category
   **Integration**.
4. Find **LG WebOS TV (bscpylgtv)** in the list and install it.
5. Restart Home Assistant.

### Manual

1. Download the `custom_components/bscpylgtv` folder from this repository.
2. Copy it into the `custom_components` directory of your Home Assistant
   configuration.
3. Restart Home Assistant.

## Setup

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **LG WebOS TV (bscpylgtv)**.
   - If your TV is on the same network, Home Assistant usually discovers it
     automatically via SSDP and you can start from the discovery card.
3. Enter the hostname or IP address of your TV and submit. The TV must be
   **turned on**.
4. **Accept the pairing prompt on the TV** — a confirmation appears on screen.
   Pairing happens via the TV prompt; PIN-based pairing is not supported.
5. The TV appears as a device with all entities attached.

If the TV stops accepting the stored pairing key, Home Assistant starts a
**re-authentication** flow automatically — just accept the new prompt on the TV.
If the TV's IP address changes, use **Reconfigure** on the config entry (or let
discovery update it).

## Turning the TV on — Wake-on-LAN / MAC address

webOS TVs cannot be woken over their websocket API, so turning the TV **on**
uses a Wake-on-LAN (WOL) magic packet:

- The TV's **MAC address is auto-detected** during pairing and on every
  successful reconnect — normally you do not have to do anything.
- When a MAC address is known, the media player and remote entities offer
  `turn_on`, and while the TV is off its entities stay available and simply
  show *off*.
- **No MAC address → no `turn_on`.** This happens when the TV was off or
  unreachable during setup and has not been seen since. Add the MAC manually:
  open the integration's **Configure** (options) flow and enter the MAC
  address (format `aa:bb:cc:dd:ee:ff`). You find it in the TV's network
  settings or in your router.

How WOL works: the integration broadcasts a UDP magic packet (port 9) to the
local network addressed to the TV's MAC; the TV's network stack wakes it even
though the websocket is down.

**Wake timing varies.** Validated on a real OLED48CXPTA: after a full
power-off (websocket gone within ~1 s) a **single WOL packet woke the TV**,
but the TV took a couple of minutes before it accepted SSAP connections
again. The integration keeps probing and reconnects automatically the
moment the TV is back — no Home Assistant restart, no reload. If wake
never happens on your set, enable **General → Quick Start+** (or *Turn On
by Wi-Fi*) in the TV's own settings and try again.

## Entities

| Platform | Entity | Category | Default | Description |
|---|---|---|---|---|
| `media_player` | LG WebOS TV *(device-named)* | — | enabled | Main entity: power, volume, mute, source (apps + inputs), play/pause/stop, next/previous, `play_media` for apps and channels |
| `remote` | Remote | — | enabled | Full remote: all library buttons plus pointer (`MOVE`, `CLICK`, `SCROLL`) and text (`TEXT`) commands |
| `notify` | Notifications | — | enabled | Toast notifications on the TV screen, optional `icon` |
| `button` | Turn screen off | — | enabled | Switch the panel off while keeping the TV running |
| `button` | Turn screen on | — | enabled | Switch the panel back on |
| `button` | Screenshot | — | enabled | Save a screenshot to `<config>/www/bscpylgtv_<deviceUUID>.jpg` |
| `button` | Reboot | Config | **disabled** | Reboot the TV |
| `number` | Backlight | Config | **disabled** | Backlight / OLED light, 0–100 |
| `number` | Contrast | Config | **disabled** | Contrast, 0–100 |
| `number` | Brightness | Config | **disabled** | Brightness, 0–100 |
| `number` | Color | Config | **disabled** | Color saturation, 0–100 |
| `number` | Sharpness | Config | **disabled** | Sharpness, 0–50 |
| `number` | Color temperature | Config | **disabled** | Color temperature, −50 to +50 |
| `select` | Picture mode | — | enabled | Live-read picture mode list (fallback list if the TV refuses the read) |
| `select` | Sound output | — | enabled | tv speaker, HDMI ARC, optical, Bluetooth, … |
| `select` | Channel | — | enabled | TV channel list (appears when Live TV was opened once) |
| `sensor` | Current app | — | enabled | Human-readable name of the running app |
| `sensor` | Volume | — | enabled | Volume in % |
| `sensor` | Power state | — | enabled | Active, Active Standby, Screen Off, Suspend, … |
| `sensor` | Current channel | Diagnostic | enabled | Channel number + name while watching Live TV |
| `switch` | TPC | Config | **disabled** | Temporal Peak Luminance Control (OLED burn-in protection) |
| `switch` | GSR | Config | **disabled** | Global Sticky Reduction (OLED burn-in protection) |

> **Caution:** TPC and GSR are OLED panel-protection mechanisms. Disabling
> them may increase burn-in risk. The switches and calibration numbers are
> disabled by default — enable them on the entity's settings page.

### Options

The integration's **Configure** flow lets you pick which **sources** (apps and
inputs) appear in the media player's source list, and set the **MAC address**
manually if it was never auto-detected.

## Services

All services target the `media_player` entity of the TV. Names and descriptions
are also visible in the UI's developer tools.

### `bscpylgtv.button`

Press a remote button:

```yaml
service: bscpylgtv.button
target:
  entity_id: media_player.lg_webos_tv
data:
  button: INFO
```

### `bscpylgtv.command`

Send a **raw SSAP endpoint** to the TV (expert usage — the response is
returned when the service is called with "respond"):

```yaml
service: bscpylgtv.command
target:
  entity_id: media_player.lg_webos_tv
data:
  command: system.launcher/open
  payload:
    target: https://www.youtube.com
```

### `bscpylgtv.select_sound_output`

```yaml
service: bscpylgtv.select_sound_output
target:
  entity_id: media_player.lg_webos_tv
data:
  sound_output: external_arc
```

### `bscpylgtv.launch_app`

Launch an app, optionally with parameters:

```yaml
service: bscpylgtv.launch_app
target:
  entity_id: media_player.lg_webos_tv
data:
  app_id: com.webos.app.youtube
  params:
    contentTarget: https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

### `bscpylgtv.take_screenshot`

Capture the current screen. Without `filename` the JPEG comes back as base64
in the service response; with `filename` it is written to that path:

```yaml
service: bscpylgtv.take_screenshot
target:
  entity_id: media_player.lg_webos_tv
data:
  filename: /config/www/tv_screen.jpg
```

```yaml
# response (no filename given)
image: "/9j/4AAQSkZJRgABAQ..."  # base64 JPEG
```

### `bscpylgtv.set_settings`

Write settings via the TV's settings API (power-user escape hatch):

```yaml
service: bscpylgtv.set_settings
target:
  entity_id: media_player.lg_webos_tv
data:
  category: picture
  settings:
    backlight: 55
    contrast: 80
```

### Standard services worth knowing

```yaml
# launch an app via the standard media_player service
service: media_player.play_media
target:
  entity_id: media_player.lg_webos_tv
data:
  media_content_type: app
  media_content_id: netflix

# tune a channel by (partial) name or number
service: media_player.play_media
target:
  entity_id: media_player.lg_webos_tv
data:
  media_content_type: channel
  media_content_id: "5 ARD"
```

```yaml
# toast notification on the TV
service: notify.lg_webos_tv_notifications
data:
  message: "Dinner is ready!"
  data:
    icon: /config/www/dinner.png
```

## Troubleshooting

- **Pairing fails or loops** — make sure the TV is on and you accept the
  prompt within the timeout. If the TV keeps rejecting a stale key, start the
  reauthentication flow from the integration's page; it re-pairs from scratch.
- **TV shows unavailable** — the TV is likely off or unreachable. With a known
  MAC address the entities show *off* instead of *unavailable* and `turn_on`
  wakes it. Wake timing varies: on a tested OLED48CXPTA the TV needed a
  couple of minutes after a full power-off before accepting connections —
  the integration recovers by itself, so give it time. If wake never
  happens, enable **Quick Start+** (or a "Turn On by Wi-Fi" equivalent) in
  the TV's settings.
- **Picture mode select shows `unknown`** — some models/firmware (verified
  on a CX OLED48CXPTA) **refuse every read of the current picture mode**
  (settings service rejects the key, config service does not carry it), so
  there is nothing to display until you set a mode from HA once. After the
  first write the value is remembered, including across restarts. The
  option list itself is the curated fallback on such models.
- **Sharpness / color temperature sliders show `unknown`** — the same
  models reject reads of those keys too, and the TV's settings push does
  not carry them. They become usable the first time you set them from HA
  (the value is then remembered across restarts); the other four picture
  sliders (backlight, contrast, brightness, color) are pushed live by the
  TV and always show the real value.
- **Channel select is empty** — the TV reports no tuner channels. Run a
  channel scan on the TV (Settings → Channels) and the select fills in on
  the next update. If you only use HDMI inputs, the channel entities are
  simply not applicable.
- **Connection went stale after TV restart / network change (zombie)** — the
  integration probes the connection every 10 s, abandons dead sockets and
  rebuilds the connection on its own; within ~15 s things should recover
  without restarting Home Assistant.
- **Picture mode list empty or unknown** — some models refuse the live enum
  read; the integration falls back to a curated list and appends an unknown
  current mode so the state still displays.
- **Channel select is heavy with huge lineups** — TVs with 1000+ channels
  produce a very long dropdown (Home Assistant UI limitation). The list is
  only rebuilt when the channel lineup actually changes; filter via
  `media_player.play_media` with a channel number if the dropdown is unwieldy.

## Known limitations

- **Firmware updates are not possible via SSAP** — webOS exposes no
  firmware-update API to websocket clients; update via the TV's own settings.
- Turning the TV **on** works only via Wake-on-LAN (the old websocket
  `power_on` API is dead on modern webOS) — see the WOL section above.
- **PIN pairing is not supported**; pairing always uses the TV prompt.
- The `command` service cannot read return values of Luna-only endpoints
  (library limitation).
- TPC/GSR switch state reads are best-effort and may show *unknown* on some
  models.

## Removing the integration

Open **Settings → Devices & Services**, open the **LG WebOS TV (bscpylgtv)**
entry, click the three dots → **Delete**. This removes the config entry, its
device and entities. Optionally also remove the integration files (HACS or
`custom_components/bscpylgtv`) and restart Home Assistant. Old pairing files
(`.storage/bscpylgtv_*.sqlite`) from v1 can be deleted manually.

## Credits

- **[chros73](https://github.com/chros73)** — author of the
  [`bscpylgtv`](https://github.com/chros73/bscpylgtv) library that powers this
  integration.
- The **Home Assistant core `webostv` maintainers** — this integration's
  architecture (coordinator, config flow, media player design) is heavily
  modeled on their work.
- **[@Xitee1](https://github.com/Xitee1)** — PR #8 *"Fix state updates dying
  due to dict iteration over apps/inputs"*.
