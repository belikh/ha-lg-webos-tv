<p align="right">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/belikh/design/latest/packages/graphics/logo/jupiter-logo-dark.svg">
    <img alt="jupiter.au" src="https://raw.githubusercontent.com/belikh/design/latest/packages/graphics/logo/jupiter-logo-light.svg" width="260">
  </picture>
</p>

# LG WebOS TV (bscpylgtv) for Home Assistant

A Home Assistant integration for LG TVs running webOS. It uses the [`bscpylgtv`](https://github.com/chros73/bscpylgtv) library by [chros73](https://github.com/chros73) and keeps one websocket connection open to the TV, so state changes arrive as they happen instead of being polled.

The design follows the built-in Home Assistant `webostv` integration. On top of that it adds picture calibration sliders, picture mode, sound output and channel selects, power-state and channel sensors, a remote with pointer and text input, screen notifications and raw SSAP commands.

<p>
  <a href="#install">Install</a> ·
  <a href="#set-up">Set up</a> ·
  <a href="#turn-the-tv-on">Turn the TV on</a> ·
  <a href="#entities">Entities</a> ·
  <a href="#services">Services</a> ·
  <a href="#troubleshooting">Troubleshooting</a> ·
  <a href="#develop">Develop</a>
</p>

<br>

---

<br>

## Features

- Setup from the UI with SSDP discovery. Pairing is a prompt on the TV; PIN pairing is not supported.
- Push updates over a supervised websocket that reconnects after TV restarts and network drops.
- Turn on through Wake-on-LAN, with the MAC address detected when the TV reports it.
- Reauthentication when the pairing key is lost, and reconfigure when the host changes.
- Diagnostics download with sensitive data redacted.
- Entities on the media player, remote, notify, button, number, select, sensor and switch platforms.
- Six services, including raw SSAP commands and screenshots.

<br>

## Install

With HACS:

[![Add to Home Assistant](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=belikh&repository=ha-lg-webos-tv&category=integration)

1. Select the button above and choose **Download**, or search for **LG WebOS TV (bscpylgtv)** in HACS.
2. Restart Home Assistant.

If the search finds nothing, open HACS, choose the three dots at the top right, then **Custom repositories**. Add `https://github.com/belikh/ha-lg-webos-tv` with category **Integration**, install it and restart.

Manually: copy the `custom_components/bscpylgtv` folder from this repository into the `custom_components` directory of your Home Assistant configuration, then restart.

<br>

## Set up

1. Go to **Settings > Devices & Services > Add Integration** and search for **LG WebOS TV (bscpylgtv)**. If the TV is on the same network, Home Assistant usually offers it as a discovered device.
2. Enter the hostname or IP address of the TV. The TV must be on.
3. Accept the pairing prompt on the TV screen.

The TV then appears as a device with its entities.

If the TV stops accepting the stored pairing key, Home Assistant starts reauthentication. Accept the new prompt on the TV. If the IP address changes, use **Reconfigure** on the config entry, or let discovery update it.

<br>

## Turn the TV on

webOS TVs cannot be woken over their websocket API, so `turn_on` sends a Wake-on-LAN magic packet (UDP, port 9) to the TV's MAC address. The TV's network stack wakes it even though the websocket is down.

- The MAC address is detected when the TV reports it during pairing or on reconnect. Some webOS 26 sets do not report it in compatibility mode. A MAC address that is already stored or entered by hand keeps working.
- With a MAC address, the media player and remote offer `turn_on`, and their entities show *off* instead of *unavailable* while the TV is off.
- Without a MAC address there is no `turn_on`. This happens when the TV was off or unreachable during setup, or does not report its MAC. Open the integration's **Configure** flow and enter it as `aa:bb:cc:dd:ee:ff`. You can find it in the TV's network settings or in your router.

Wake timing varies. On an OLED48CXPTA, a single packet woke the TV after a full power-off, but it took a couple of minutes before it accepted connections. The integration keeps probing and reconnects when the TV is back, without a restart or reload. If the TV never wakes, enable **General > Quick Start+** (or *Turn On by Wi-Fi*) in the TV's own settings.

<br>

## Entities

| Platform | Entity | Category | Default | Description |
|---|---|---|---|---|
| `media_player` | LG WebOS TV *(device-named)* | — | enabled | Main entity: power, volume, mute, source (apps + inputs), play/pause/stop, next/previous, `play_media` for apps and channels |
| `remote` | Remote | — | enabled | Full remote: all library buttons plus pointer (`MOVE`, `CLICK`, `SCROLL`) and text (`TEXT`) commands |
| `notify` | Notifications | — | enabled | Toast notifications on the TV screen, optional `icon` |
| `button` | Turn screen off | — | enabled | Switch the panel off while keeping the TV running |
| `button` | Turn screen on | — | enabled | Switch the panel back on |
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

> [!WARNING]
> TPC and GSR are OLED panel-protection mechanisms. Disabling
> them may increase burn-in risk. The switches and calibration numbers are
> disabled by default — enable them on the entity's settings page.

<br>

## Configuration


The integration's **Configure** flow lets you pick which **sources** (apps and
inputs) appear in the media player's source list, and set the **MAC address**
manually if it was never auto-detected. It also holds the experimental
soundbar volume settings below.

### Soundbar volume (experimental, off by default)

On an ARC, optical or external-speaker sound output the TV forwards volume
up, down and mute to the soundbar but cannot read or set its level. The media
player therefore shows no volume level and no slider on those outputs, and
`volume_up`, `volume_down` and `volume_mute` still reach the soundbar.

Turn on **Experimental: soundbar volume by key presses** in the options to get
the slider back. Setting a volume then presses volume-down until the soundbar
is at its minimum, and presses volume-up once per step to the target. The
level shown is the integration's estimate, not a reading from the soundbar.

| Option | Default | Meaning |
|---|---|---|
| Soundbar press interval | 320 ms | Time between key presses. Presses sent faster than the soundbar accepts are lost. |
| Extra volume-down presses when homing | 5 | Added to the estimated level when pressing down, so the soundbar still reaches its minimum if the estimate is too high. Each one adds one interval to every volume change. |
| Soundbar volume steps | 40 | Steps from minimum to maximum. The slider maps 0 to 100 % onto 0 to this value. |

How it behaves:

- The first set after a restart homes from the full step count, because the
  estimate starts empty.
- A newer volume set stops the one still running after its current press.
- Changing the volume with the soundbar's own remote, or with the TV remote,
  is not tracked. The next set re-homes using the extra presses.
- Setting 50 % on 40 steps takes about (estimate + 5 + 20) × 320 ms.
- Measured on an LG SN4 over ARC (15 presses from 0): 13 reached at 220 and
  240 ms, 15 at 267 and 370 ms, and 30 of 30 at 320 ms. Test your own
  soundbar before lowering the interval.

<br>

## Services

All services target the `media_player` entity of the TV. The UI's developer tools show the same names and descriptions.

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
  filename: /media/tv_screen.jpg
```

The `filename` path is validated against Home Assistant's allowed paths
(`hass.config.is_allowed_path`) before writing. It must resolve inside an
existing allowed directory: the media directory (`/media`) and
`<config>/www` are allowed by default; add other directories to
`allowlist_external_dirs` if needed. Paths outside the allowed directories
are rejected with a `ServiceValidationError`, so the service cannot
overwrite arbitrary files on the system.

**Do not write screenshots to `<config>/www`.** Home Assistant serves that
folder at `/local/` without authentication, so anyone who can reach your
instance could view the picture. Use `/media` (or another allow-listed
private directory) instead. The integration no longer has a Screenshot
button for the same reason; call this service from an automation or script.

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

### Standard services

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
    icon: /media/dinner.png
```

<br>

## Troubleshooting

<details><summary><b>Pairing, firmware and connection problems</b></summary>

- **Pairing fails or loops** — make sure the TV is on and you accept the
  prompt within the timeout. If the TV keeps rejecting a stale key, start the
  reauthentication flow from the integration's page; it re-pairs from scratch.
  On webOS 25 sets (LG C3/C5 and similar) v2.0.2 fixes pairing entirely:
  earlier versions never showed the prompt because the TV ignores the
  library's `hello` handshake (issue #11).
- **webOS 26 sets (firmware 43.x) reject pairing, or an existing setup
  stopped working after a firmware update** — some sets reject the legacy
  signed manifest. v2.0.4 retries with an unsigned manifest after the known
  registration rejection, remembers that compatibility mode, and avoids
  requesting software information that is unavailable in that mode. If the
  stored pairing key is no longer registered, Home Assistant starts
  reauthentication. Use **Reconfigure** to deliberately check whether the
  normal signed manifest works again. This is a different firmware behaviour
  from the webOS 25 `hello` bug fixed in v2.0.2.
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

</details>

### Report a problem

[Open an issue](https://github.com/belikh/ha-lg-webos-tv/issues/new/choose) and
fill in the bug report form. It asks for the TV model, the webOS version and
two files that let the maintainer see what the integration did:

1. **Debug log.** Open **Settings > Devices & services > LG WebOS TV
   (bscpylgtv)**, choose **Enable debug logging** from the three-dot menu,
   repeat the problem, then choose **Disable debug logging**. The browser
   downloads `home-assistant_bscpylgtv_<date>.log`. The log holds only the
   period between the two clicks. The integration does not log the pairing
   key, but connection errors from the library can include the TV's local IP
   address, so read the file before posting.
2. **Diagnostics.** Open the TV's device page and choose **Download
   diagnostics**. The file lists the integration, library and Home Assistant
   versions, the TV's model and power state, and the current app and channel.
   It redacts the pairing key, IP address, MAC address and unique ID.

To keep debug logging on across restarts, add this to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.bscpylgtv: debug
    bscpylgtv: debug
```

<br>

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

<br>

## Remove

Open **Settings > Devices & Services**, open the **LG WebOS TV (bscpylgtv)** entry, choose the three dots, then **Delete**. This removes the config entry, its device and its entities. To remove the code too, uninstall through HACS or delete `custom_components/bscpylgtv`, then restart. Old pairing files from v1 (`.storage/bscpylgtv_*.sqlite`) can be deleted by hand.

<br>

## Develop

Tests run against a pinned Home Assistant version with [uv](https://docs.astral.sh/uv/):

```sh
uv sync          # create .venv from uv.lock
uv run pytest
uv run ruff check custom_components tests
uv run mypy
```

`pyproject.toml` holds the dev dependency group (pytest-homeassistant-custom-component, bscpylgtv, ruff, mypy) and `uv.lock` pins the full tree. After changing the `bscpylgtv` pin in `manifest.json`, update the dev group and run `uv lock` in the same change.

<br>

## Licence

MIT. See [LICENSE](LICENSE). Release history is in [CHANGELOG.md](CHANGELOG.md).

<br>

## Credits

- **[chros73](https://github.com/chros73)** — author of the
  [`bscpylgtv`](https://github.com/chros73/bscpylgtv) library that powers this
  integration.
- The **Home Assistant core `webostv` maintainers** — this integration's
  architecture (coordinator, config flow, media player design) is heavily
  modeled on their work.
- **[@Xitee1](https://github.com/Xitee1)** — PR #8 *"Fix state updates dying
  due to dict iteration over apps/inputs"*.
- **@AquaCobell** & **@jerielsr** — issue #14, reporting entities unavailable
  after pairing on webOS 26 sets (blacklisted-certificate rejection).
- **@Ramss3s** — issue #13, reporting webOS 26 pairing failure on
  firmware 43.21.71.
- **@NoCleverMoniker** & **@starast** — issue #11, reporting the webOS 25
  pairing timeout caused by the library's `hello` handshake.
- **@brei-er** — PR #12, robust webOS 26 manifest compatibility
  (unsigned-manifest fallback, persisted compatibility mode).
- **@frenck** — security reviews that prompted `is_allowed_path` validation
  on the `take_screenshot` filename and notify `icon` path, and removing the
  screenshot button that wrote into the publicly served `www` directory.

<br>

<p align="right"><sub>jupiter.au</sub></p>
