---
title: Why external outputs have no volume level
summary: The TV forwards volume keys to a soundbar and cannot read its level, so the integration estimates it.
order: 20
audience: users
status: draft
---

On `external_arc`, `external_optical`, `external_speaker`, `tv_external_speaker` and `tv_speaker_external_arc`, the TV only counts key presses and sends them to the soundbar. It has no reading of the soundbar level and no way to set it.

Because of that, the media player hides the volume slider and the volume level on these outputs. Up, down and mute still work.

## The experimental mode

The option **Experimental: soundbar volume by key presses** builds a slider from presses. A volume set presses volume-down until the soundbar bottoms out, then volume-up once per step to the target. The integration remembers the level it believes the soundbar has. That level is an estimate, and any change made outside Home Assistant makes it wrong until the next set re-homes the soundbar.

The mode is off by default because it sends dozens of key presses for one change and presses can be lost on a slow soundbar. See [[guides/soundbar-volume]] for timing.

:::see-also
- [[reference/sound-outputs]]
- [[reference/options]]
:::
