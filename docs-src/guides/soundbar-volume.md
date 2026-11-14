---
title: Control soundbar volume
summary: Switch sound outputs and turn on the experimental volume slider for a soundbar on ARC, optical or an external speaker.
order: 30
audience: users
status: draft
---

On an external output the TV forwards volume keys to the soundbar and cannot read its level. The media player then shows no volume level and no slider. `volume_up`, `volume_down` and `volume_mute` still reach the soundbar.

## Switch the sound output

Use the **Sound output** select, or call the service:

```yaml title="Send audio to a soundbar on HDMI ARC"
service: bscpylgtv.select_sound_output
target:
  entity_id: media_player.lg_webos_tv
data:
  sound_output: external_arc
```

[[reference/sound-outputs]] lists every value. The select adds the output the TV currently reports when it is not in the list.

## Get the volume slider back

1. Open **Settings > Devices & Services > LG WebOS TV (bscpylgtv)** and choose **Configure**.
2. Turn on **Experimental: soundbar volume by key presses**.
3. Adjust the three timing options if your soundbar needs it. Defaults are in [[reference/options]].

Setting a volume then presses volume-down until the soundbar is at its minimum, and presses volume-up once per step to the target. The soundbar does not report its level, so the integration shows its own estimate. While the mode is active the media player gains a `soundbar_steps` attribute.

## What to expect

- The first set after a restart homes from the full step count, because the estimate starts empty.
- A newer volume set stops the one still running after its current press.
- Changes made with the remote of the soundbar or of the TV are not tracked. The next set re-homes with the extra presses.
- Setting 50 % on 40 steps takes about (estimate + 5 + 20) x 320 ms.

## Tune the press interval

Presses sent faster than the soundbar accepts are lost. On an LG SN4 over ARC, 15 presses from 0 reached 13 at 220 ms and 240 ms, 15 at 267 ms and 370 ms, and 30 of 30 at 320 ms. Test your soundbar before you lower the interval.

:::see-also
- [[concepts/sound-outputs]]
- [[reference/options]]
:::
