---
title: How it works
summary: The connection, pairing, reconnect and wake behavior of the integration.
order: 10
audience: developers
status: draft
---

The integration keeps one websocket open per TV and subscribes to state pushes. It does not poll for state.

## Connection and subscriptions

A coordinator owns the bscpylgtv client. It subscribes to `system_info`, `software_info`, `power`, `current_app`, `muted`, `volume`, `apps`, `inputs`, `sound_output` and `picture_settings`. The channel list and current channel subscribe lazily once Live TV is in the foreground, with 15 attempts spaced 2 s apart. In [[term:Compatibility mode]] the integration drops `software_info`.

The integration is `local_push`, with `config_flow` and SSDP discovery on `urn:lge-com:service:webos-second-screen:1`.

## Watchdog

The coordinator interval of 10 s drives a watchdog that never fetches state. Each tick probes a healthy connection (5 s budget) and rebuilds a dead one. Commands time out after 8 s and a reconnect after 15 s. After a TV restart or network change, things recover in about 15 s.

## Pairing

The TV shows a prompt and returns a [[term:Pairing key]] on accept. The integration stores it as `client_key` in the config entry. Two firmware behaviors shape the flow:

- webOS 25 ignores the `hello` handshake of the library, so a connect that requests it hangs until the caller's timeout. The integration bounds the probe to 5 s (fixed in 2.0.2).
- webOS 26 firmware 43.x can reject the signed manifest. The integration retries with an unsigned manifest, stores `unsigned_manifest`, and keeps using it (from 2.0.4).

A key the TV no longer accepts raises reauthentication.

## Power and wake

The websocket is closed while the TV is off, so `turn_on` cannot use it. `turn_on` sends [[term:Wake-on-LAN]] to UDP port 9 and asks the coordinator to reconnect as soon as the TV boots. The watchdog keeps retrying every 10 s in any case. In art standby (`Screen Off`) the socket stays open, so a command can wake the screen.

## Entity availability

With a stored MAC address, entities show `off` while the TV is off. Without one they show `unavailable`. The media player restores its supported features after a restart while the TV is off.

:::see-also
- [[concepts/sound-outputs]]
- [[concepts/limitations]]
:::
