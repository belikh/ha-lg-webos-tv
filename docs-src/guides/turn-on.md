---
title: Turn the TV on
summary: Wake a TV with Wake-on-LAN and set the MAC address when it was not detected.
order: 10
audience: users
status: draft
---

`turn_on` sends a [[term:Wake-on-LAN]] magic packet (UDP, port 9) to the MAC address of the TV. A webOS TV cannot be woken over its websocket API, so this is the only way.

## Check that turn on is offered

The media player and the remote offer `turn_on` only when a MAC address is stored. The integration detects it when the TV reports it during pairing or on reconnect.

- With a MAC address, entities show `off` while the TV is off.
- Without one, entities show `unavailable` and there is no `turn_on`. This happens when the TV was off or unreachable during setup, or when it does not report its MAC. Some webOS 26 sets do not report it in [[term:Compatibility mode]].

## Enter the MAC address by hand

1. Find the address in the network settings of the TV or in your router. Use the format `aa:bb:cc:dd:ee:ff`.
2. Open **Settings > Devices & Services > LG WebOS TV (bscpylgtv)** and choose **Configure**.
3. Enter the address in **MAC address** and submit.

An invalid value fails with `Invalid MAC address. Use the format aa:bb:cc:dd:ee:ff.` A stored or hand-entered address keeps working.

## Wake timing

Timing varies by set. On an OLED48CXPTA one packet woke the TV after a full power-off, and the TV took a couple of minutes to accept connections. The integration keeps probing and reconnects when the TV is back, with no restart or reload.

If the TV never wakes, enable **General > Quick Start+** (or **Turn On by Wi-Fi**) in the settings of the TV.

## Turn on from an automation

```yaml title="Turn the TV on"
service: media_player.turn_on
target:
  entity_id: media_player.lg_webos_tv
```

Screen off is separate from power off. When the TV is on with the screen off, `turn_on` on the remote wakes the screen over the websocket. Use the **Turn screen on** button for the same effect.

:::see-also
- [[reference/options]]
- [[guides/troubleshoot]]
:::
