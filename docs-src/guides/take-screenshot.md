---
title: Take a screenshot
summary: Capture the TV screen to a file in /media or as base64 in a service response.
order: 40
audience: users
status: draft
---

`bscpylgtv.take_screenshot` captures the current screen as a JPEG.

## Save to a file

```yaml title="Write /media/tv_screen.jpg"
service: bscpylgtv.take_screenshot
target:
  entity_id: media_player.lg_webos_tv
data:
  filename: /media/tv_screen.jpg
```

Home Assistant checks the path with `hass.config.is_allowed_path` before it writes. The path must resolve inside an existing allowed directory. `/media` and `<config>/www` are allowed by default. Add other directories to `allowlist_external_dirs`.

:::warning Do not write to the www folder
Home Assistant serves `<config>/www` at `/local/` without authentication. Anyone who can reach your instance can open the picture. Write screenshots to `/media` or another private allowed directory.
:::

## Get the image in the response

Leave out `filename` and call the service with a response variable:

```yaml title="Response"
image: "/9j/4AAQSkZJRgABAQ..."  # base64 JPEG
```

## Errors

| Message | Cause | Fix |
| --- | --- | --- |
| `Screenshot path /x.jpg is not allowed.` | The path is outside every allowed directory. | Use `/media` or add the directory to `allowlist_external_dirs`. |
| `Could not write the screenshot file to /media/x.jpg.` | The directory is missing or not writable. | Create the directory and check permissions. |

The integration has no Screenshot button. It was removed because it wrote into the public `www` folder. Call the service from an automation or script.

:::see-also
- [[reference/services]]
:::
