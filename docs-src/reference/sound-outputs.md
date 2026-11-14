---
title: Sound outputs
summary: The sound output values the select and the select_sound_output service accept.
order: 50
audience: users
status: draft
---

The select lists these values and adds the output the TV currently reports when it is missing.

| Value | Meaning | Volume control |
| --- | --- | --- |
| `tv_speaker` | TV speakers | Absolute |
| `headphone` | Headphone jack | Absolute |
| `external_arc` | Soundbar on HDMI ARC | Step and mute |
| `external_optical` | Optical output | Step and mute |
| `external_speaker` | External speaker | Step and mute |
| `tv_external_speaker` | TV speakers plus an external speaker | Step and mute |
| `tv_speaker_external_arc` | TV speakers plus a soundbar on ARC (WOW Orchestra, from 2.1.1) | Step and mute |
| `lineout` | Line out | None |
| `bt_soundbar` | Bluetooth soundbar | Step and mute |
| `lgSoundSync` | LG Sound Sync | Step and mute |
| `wisa_speaker` | WiSA speaker | Step and mute |
| `usb_speaker` | USB speaker | Step and mute |

Absolute volume means the slider works. Step and mute means `volume_up`, `volume_down` and `volume_mute` work and the slider is hidden. The experimental slider in [[guides/soundbar-volume]] applies to the five outputs from `external_arc` to `tv_speaker_external_arc`, not to the Bluetooth, Sound Sync, WiSA and USB outputs. When the TV reports no output, the media player offers absolute volume.

:::see-also
- [[concepts/sound-outputs]]
- [[guides/soundbar-volume]]
:::
