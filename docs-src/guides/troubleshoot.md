---
title: Troubleshoot
summary: Causes and fixes for pairing failures, unavailable TVs and empty or unknown entities.
order: 50
audience: users
status: draft
---

Find your symptom, then follow its fix. Collect logs with [[guides/report-a-problem]] when none applies.

## Pairing fails or loops

Make sure the TV is on and accept the prompt before the timeout. If the TV keeps rejecting a stale key, start reauthentication from the integration page. It pairs again from scratch.

On webOS 25 sets (LG C3, C5 and similar), versions before 2.0.2 never showed the prompt, because the TV ignores the `hello` handshake of the library (issue #11). Update to 2.0.2 or later.

## webOS 26 rejects pairing, or a working setup stopped after a firmware update

Some webOS 26 sets (firmware 43.x) reject the legacy signed manifest. From 2.0.4 the integration retries with an unsigned manifest after the known registration rejection. It remembers this [[term:Compatibility mode]] and skips the software information request, which that mode does not provide.

If the stored [[term:Pairing key]] is no longer registered, Home Assistant starts reauthentication. Use **Reconfigure** to check whether the normal signed manifest works again. This differs from the webOS 25 `hello` problem.

## The TV shows unavailable

The TV is off or unreachable. With a known MAC address, entities show `off` and `turn_on` wakes the TV. See [[guides/turn-on]]. On a tested OLED48CXPTA the TV needed a couple of minutes after a full power-off before it accepted connections, and the integration recovered on its own.

## The connection went stale after a TV restart or network change

The integration probes the connection every 10 s, drops dead sockets and rebuilds the connection. Recovery takes about 15 s and needs no restart of Home Assistant.

## Picture mode shows unknown

Some models refuse every read of the current picture mode. Tested on an OLED48CXPTA: the settings service rejects the key and the config service does not carry it. Set a mode from Home Assistant once. The value is remembered across restarts.

The option list is a fixed fallback on such models. When the live read fails, the integration appends the unknown current mode so the state still displays.

## Sharpness and color temperature show unknown

The same models reject reads of those keys, and the settings push of the TV does not carry them. They work after you set them once from Home Assistant, and the value is remembered across restarts. Backlight, contrast, brightness and color are pushed live and always show the real value.

## The channel select is empty

The TV reports no tuner channels. Run a channel scan in **Settings > Channels** on the TV. The select fills on the next update. If you use only HDMI inputs, the channel entities do not apply.

## The channel select is very long

A TV with 1000 or more channels produces a long dropdown, which is a Home Assistant UI limit. The list is rebuilt only when the lineup changes. Use `media_player.play_media` with a channel number instead (see [[guides/launch-apps-and-channels]]).

## TPC or GSR show unknown

The state reads of these switches are best-effort and return `unknown` on some models.

## Service errors

| Message | Cause | Fix |
| --- | --- | --- |
| `Unable to connect to device <name>. Turn the TV on, or configure its MAC address in the integration options so it can be woken remotely.` | The TV is off and no MAC address is stored. | Turn the TV on, or set the MAC address in [[reference/options]]. |
| `Error calling <func> for device <name>: Device is off and cannot be controlled.` | The service needs a connected TV. | Turn the TV on first. |
| `Unknown button <name>.` | The button is not in the library list. | Use a name from [[reference/remote-commands]]. |
| `Icon path <path> is not allowed.` | The notify icon is outside the allowed directories. | Use a path under `/media` or an entry of `allowlist_external_dirs`. |
| `Icon <path> not found when sending notification for device <name>` | The icon file does not exist. | Check the path. |

:::see-also
- [[concepts/limitations]]
- [[guides/report-a-problem]]
:::
