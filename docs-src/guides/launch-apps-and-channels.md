---
title: Launch apps and tune channels
summary: Open an app, a channel or a URL on the TV from the media player, the selects or a service.
order: 20
audience: users
status: draft
---

The media player starts apps and tunes channels with `media_player.play_media`.

## Launch an app

```yaml title="Launch Netflix"
service: media_player.play_media
target:
  entity_id: media_player.lg_webos_tv
data:
  media_content_type: app
  media_content_id: netflix
```

The integration also launches an app when `media_content_id` is a full app id such as `com.webos.app.youtube`, whatever the content type. To pass parameters, use [[reference/services#bscpylgtvlaunch_app|launch_app]].

## Tune a channel

```yaml title="Tune a channel by number and name"
service: media_player.play_media
target:
  entity_id: media_player.lg_webos_tv
data:
  media_content_type: channel
  media_content_id: "5 ARD"
```

The integration matches `media_content_id` in this order: exact channel number, exact channel name (case-insensitive), then a partial name. An unmatched value fails with `Channel 5 ARD not found in the channel list.`

## Pick a source

`media_player.select_source` takes an app or input title from the source list. Choose which titles appear in [[reference/options]]. An unknown title fails with `Source <name> not found in the sources list for <tv>.`

## Open a URL

```yaml title="Open a web page"
service: bscpylgtv.command
target:
  entity_id: media_player.lg_webos_tv
data:
  command: system.launcher/open
  payload:
    target: https://www.youtube.com
```

:::see-also
- [[reference/services]]
- [[reference/entities]]
:::
