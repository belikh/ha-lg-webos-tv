# Release notes — v2.0.0

**LG WebOS TV (bscpylgtv) for Home Assistant**

Version 2.0.0 is a major release. Following semantic versioning, the major
bump signals **breaking changes**: some entities, services and identifiers
change in ways that may require you to update dashboards, automations and
scripts. Everything you need to migrate is in the next section — it is worth
reading even if you skim the rest.

## Changes that affect your Home Assistant configuration

### 1. Entity & device migration (unique IDs now use the device UUID)

The integration previously identified your TV by its **IP address**, which
broke whenever the TV's address changed. Config entries, entities and devices
are now anchored to the TV's stable `deviceUUID`:

| What | Before (v1) | After (v2) |
|---|---|---|
| Config entry unique_id | TV IP (e.g. `192.168.1.42`) | `<deviceUUID>` |
| `media_player` unique_id | TV IP (e.g. `192.168.1.42`) | `<deviceUUID>` |
| Other entities unique_id | `<config-entry-id>_<name>` | `<deviceUUID>_<key>` |
| Device identifier | `(bscpylgtv, <IP>)` | `(bscpylgtv, <deviceUUID>)` |

Consequences and cleanup guidance:

- **Old entities are orphaned.** After upgrading, delete the stale device via
  **Settings → Devices & Services → your TV → Delete device** (or remove the
  leftover entities in the entity registry / developer tools). New entities
  are created fresh under the UUID-based device.
- **History and statistics break** for the old entity IDs; long-term statistics
  can be re-linked via the entity registry, but history charts and cards need
  to point at the new entities.
- **Automations and scripts that reference entities by `entity_id`** (e.g.
  `media_player.lg_webos_tv`) usually keep working, because `entity_id` is
  name-based and the friendly name carries over. Anything that references
  entities by `unique_id` or device identifier must be updated.
- The config entry's unique_id migrates automatically the first time the
  integration connects to the TV.

### 2. Key storage migration

The pairing key previously lived in a SQLite file under
`.storage/bscpylgtv_<ip>.sqlite` in your Home Assistant configuration
directory. In v2 the key is stored **inside the config entry** itself:

- On first start after the upgrade, the old file is **read once
  automatically** and the key is moved into the config entry.
- The old `.storage/bscpylgtv_<ip>.sqlite` file is **left in place** — it is
  unused from now on and safe to delete later.
- If the file is missing or unreadable, the integration falls back silently
  and Home Assistant **prompts you to re-pair** automatically — just accept
  the prompt on the TV.

### 3. Removed entities & services

- **`oled_light` number — removed.** There is no such webOS setting key: on
  OLED panels the OLED light value *is* the `backlight` setting. Use the
  **backlight** number entity — it controls the same thing.
- **`reboot_soft` and `show_screen_saver` buttons — removed.** Both call
  webOS APIs that are dead on modern firmware versions.
- **`switch.ai_picture_pro` — removed.** This entity never had a working
  backend (phantom).
- **`launch_app_with_params` service — merged into `launch_app`.** Pass the
  extra parameters in the new `params` field:

  ```yaml
  # before
  service: bscpylgtv.launch_app_with_params
  data:
    app: youtube
    params: {target: "https://youtube.com/tv"}

  # after
  service: bscpylgtv.launch_app
  data:
    app_id: youtube
    params: {target: "https://youtube.com/tv"}
  ```

- **`command` service — semantic change.** It now sends a **raw SSAP
  endpoint** instead of calling a library method by name. **Old automations
  using method names break.** Before/after:

  ```yaml
  # before (v1: library method name)
  service: bscpylgtv.command
  data:
    command: system_info

  # after (v2: raw SSAP endpoint + optional payload)
  service: bscpylgtv.command
  data:
    command: system.launcher/open
    payload:
      target: https://www.google.com
  ```

- New services join the list: `button`, `select_sound_output`,
  `take_screenshot` (and `set_settings` continues). See the README for all of
  them.

### 4. `turn_on` is Wake-on-LAN first

The websocket `power_on` API is dead on modern webOS, so turning the TV on is
now done with a Wake-on-LAN magic packet sent by the integration itself:

- This **requires the TV's MAC address**, which is **auto-detected** during
  pairing and on every reconnect — for most setups nothing to do.
- If the MAC is unknown (e.g. the TV was off during setup and has not been
  seen since), you can **enter it manually** in the integration's **options
  flow** (Configure → MAC address).
- When no MAC is known, the `turn_on` feature is **hidden** from the media
  player and remote, and the TV shows as **unavailable** while it is off.
- **Note:** wake timing varies by TV — on a real OLED48CXPTA a single WOL
  packet woke the TV after a full power-off, but it took a couple of minutes
  before connections were accepted again; the integration reconnects
  automatically once it is back. If wake never happens, enable **Quick
  Start+** (or "Turn On by Wi-Fi") in the TV's settings — see the README's
  troubleshooting section.

### 5. Repository rename — no action needed for HACS users

The repository is now **belikh/ha-lg-webos-tv**. Old GitHub URLs redirect to
the new location, and HACS follows redirects — **existing installations keep
working without any action**. If you manually pinned the old URL somewhere,
update it at your convenience.

## What else is new

- **Fixes #9 — "Doesn't work after TV was off":**
  - Entities no longer stay unavailable until you restart Home Assistant. A
    supervised connection watchdog reconnects on its own when the TV comes
    back (and with a known MAC the media player stays available showing OFF
    instead of dropping out at all).
  - Reloading the integration now actually works — even when the previous
    connection is wedged — without needing a full Home Assistant restart.
  - Sound output no longer snaps back to `tv_speaker` after the TV returns:
    values that changed on the TV while it was unreachable are re-synced from
    the fresh connection.
- Supervised push connection: automatic reconnect after TV restarts and
  network changes, zombie-connection detection and self-healing.
- Reauthentication flow (stale pairing keys) and reconfigure flow (host
  changes); discovery updates a changed IP in place instead of duplicating.
- Options flow: filter the media player source list, manual MAC entry.
- New entities: channel select + current-channel sensor (Live TV), full
  `remote` (all library buttons, pointer `MOVE`/`CLICK`/`SCROLL`, text input),
  screen on/off buttons, `tpc`/`gsr` OLED-protection switches.
- Picture-mode options are read live from the TV (curated fallback list when
  the model refuses the read).
- Screenshots return base64 data or write to a file; a screenshot button
  saves to `www/`.
- Redacted diagnostics, icons, complete English translations, honest
  `quality_scale.yaml` and a full test suite.

## Downgrade protection

Config entries created or migrated by v2 use config-entry schema version 2.
Home Assistant **refuses to load a v2 entry with the old v1 code** — if you
roll back the integration files, set the TV up again from scratch (or restore
your v1 `.storage` backup) rather than mixing versions.

## Thanks

- **@Xitee1** for PR #8 — "Fix state updates dying due to dict iteration over apps/inputs"
  — a state-update killer that had been eluding everyone — and for reporting
  issue #9 ("Doesn't work after TV was off"), whose three symptoms this
  release closes and regresses against in the test suite.
- **chros73**, author of the
  [bscpylgtv](https://github.com/chros73/bscpylgtv) library this integration
  is built on.
- The **Home Assistant core `webostv` maintainers**, whose integration served
  as the architecture reference for this rewrite.
