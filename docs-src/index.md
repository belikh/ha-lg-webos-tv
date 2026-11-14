---
title: LG WebOS TV (bscpylgtv)
summary: A Home Assistant integration that controls LG webOS TVs over one push websocket per TV.
---

The integration connects Home Assistant to an LG TV that runs webOS. It uses the [bscpylgtv](https://github.com/chros73/bscpylgtv) library by chros73 and keeps one websocket open to the TV, so state changes arrive as they happen.

Its design follows the built-in Home Assistant `webostv` integration. It adds picture calibration sliders, picture mode, sound output and channel selects, power-state and channel sensors, a remote with pointer and text input, screen notifications and raw [[term:SSAP]] commands.

## What you get

- Setup from the UI with SSDP discovery and a pairing prompt on the TV.
- A supervised connection that reconnects after TV restarts and network drops.
- Turn on through [[term:Wake-on-LAN]], with the MAC address detected when the TV reports it.
- Reauthentication when the [[term:Pairing key]] is lost, and reconfigure when the host changes.
- Entities on 8 platforms: media player, remote, notify, button, number, select, sensor and switch.
- Six services, including raw SSAP commands and screenshots.
- A diagnostics download with the pairing key, host, MAC address and unique ID redacted.

## Where to start

:::see-also
- [[start/install]]
- [[start/set-up]]
- [[reference/entities]]
- [[reference/services]]
- [[guides/troubleshoot]]
:::
