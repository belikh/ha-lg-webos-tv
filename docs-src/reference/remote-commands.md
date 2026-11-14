---
title: Remote commands
summary: Button names, aliases and the pointer and text commands that remote.send_command accepts.
order: 30
audience: users
status: draft
---

`remote.send_command` and `bscpylgtv.button` take button names from the bscpylgtv library. The library has 77 names. Names are case-insensitive.

## Aliases

| Name | Sent as |
| --- | --- |
| `SELECT` | `ENTER` |
| `VOLUME_UP` | `VOLUMEUP` |
| `VOLUME_DOWN` | `VOLUMEDOWN` |

## Common buttons

`LEFT`, `RIGHT`, `UP`, `DOWN`, `HOME`, `BACK`, `ENTER`, `MENU`, `EXIT`, `INFO`, `DASH`, `ASTERISK`, `CC`, `MUTE`, `VOLUMEUP`, `VOLUMEDOWN`, `CHANNELUP`, `CHANNELDOWN`, `PLAY`, `PAUSE`, `STOP`, `RED`, `GREEN`, `BLUE`, `YELLOW`, `POWER` and `0` to `9`.

## Pointer and text commands

| Command | Format | Effect |
| --- | --- | --- |
| `CLICK` | `CLICK` | Click at the pointer. |
| `MOVE` | `MOVE:dx,dy` or `MOVE:dx,dy,down` | Move the pointer by `dx`, `dy`. `down` is 0 or 1 and defaults to 0. |
| `SCROLL` | `SCROLL:dx,dy` | Scroll by `dx`, `dy`. |
| `TEXT` | `TEXT:some text` | Type text into the focused field. Case is kept. |

A malformed command fails with `Unknown button <command>.`

```yaml title="Move the pointer, click, type"
service: remote.send_command
target:
  entity_id: remote.lg_webos_tv_remote
data:
  command:
    - "MOVE:100,50"
    - CLICK
    - "TEXT:Dark"
```

The remote accepts a list and sends the commands in order.

:::see-also
- [[reference/services]]
:::
