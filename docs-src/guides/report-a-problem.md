---
title: Report a problem
summary: Collect a debug log and a diagnostics file for a bug report.
order: 60
audience: users
status: draft
---

Open an [issue](https://github.com/belikh/ha-lg-webos-tv/issues/new/choose) and fill in the bug report form. It asks for the TV model, the webOS version and two files.

## Collect the debug log

1. Open **Settings > Devices & services > LG WebOS TV (bscpylgtv)**.
2. Choose **Enable debug logging** from the three-dot menu.
3. Repeat the problem.
4. Choose **Disable debug logging**. The browser downloads `home-assistant_bscpylgtv_<date>.log`.

The log covers only the time between the two clicks. The integration does not log the pairing key. Connection errors from the library can include the local IP address of the TV, so read the file before you post it.

To keep debug logging on across restarts, add this to `configuration.yaml`:

```yaml title="configuration.yaml"
logger:
  logs:
    custom_components.bscpylgtv: debug
    bscpylgtv: debug
```

## Download diagnostics

1. Open the device page of the TV.
2. Choose **Download diagnostics**.

The file lists the integration, library and Home Assistant versions, the model and power state of the TV, and the current app and channel. It redacts the pairing key, host, MAC address and unique ID.

:::see-also
- [[guides/troubleshoot]]
:::
