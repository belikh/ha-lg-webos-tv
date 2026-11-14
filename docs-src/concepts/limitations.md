---
title: Limitations
summary: What the integration cannot do because of webOS or the library.
order: 30
audience: users
status: draft
---

- **Firmware updates.** webOS has no firmware-update API for websocket clients. Update from the settings of the TV.
- **Turn on.** It works only through [[term:Wake-on-LAN]]. The websocket `power_on` call is dead on current webOS.
- **PIN pairing.** Pairing always uses the prompt on the TV.
- **Luna-only endpoints.** The `command` service cannot read their return values (library limitation).
- **TPC and GSR state.** Reads are best-effort and show `unknown` on some models.
- **Picture settings reads.** Some models refuse reads of picture mode, sharpness and color temperature until you set them once. See [[guides/troubleshoot]].
- **Soundbar volume.** The level is an estimate. See [[concepts/sound-outputs]].
