---
title: Install
summary: Add the integration to Home Assistant with HACS or by copying one folder.
order: 10
audience: users
status: draft
---

Install with HACS, then restart Home Assistant.

## Install with HACS

[![Add to Home Assistant](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=belikh&repository=ha-lg-webos-tv&category=integration)

1. Select the badge above and choose **Download**. You can also search for **LG WebOS TV (bscpylgtv)** in HACS.
2. Restart Home Assistant.

If the search finds nothing, add the repository by hand:

1. In HACS, open the three-dot menu at the top right and choose **Custom repositories**.
2. Enter [github.com/belikh/ha-lg-webos-tv](https://github.com/belikh/ha-lg-webos-tv) with category **Integration**.
3. Install the integration and restart Home Assistant.

## Install by hand

1. Copy the `custom_components/bscpylgtv` folder from the [repository](https://github.com/belikh/ha-lg-webos-tv) into the `custom_components` directory of your Home Assistant configuration.
2. Restart Home Assistant.

```text title="Resulting layout"
<config>/custom_components/bscpylgtv/manifest.json
```

:::see-also
- [[start/set-up]]
:::
