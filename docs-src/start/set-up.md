---
title: Set up a TV
summary: Add a TV to Home Assistant, accept the pairing prompt and recover from a lost key or a new IP address.
order: 20
audience: users
status: draft
---

Add the TV from **Settings > Devices & Services**. The TV must be on and on the same network as Home Assistant.

## Add a TV

[![Add integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=bscpylgtv)

1. Select the badge above, or go to **Settings > Devices & Services > Add Integration** and search for **LG WebOS TV (bscpylgtv)**. Home Assistant often lists the TV as a discovered device already.
2. Enter the hostname or IP address of the TV and select **Submit**.
3. Accept the pairing prompt on the TV screen, then select **Submit** in Home Assistant.

The TV appears as a device with its entities. See [[reference/entities]] for the list and which entities start disabled.

PIN pairing is not supported. Pairing always uses the prompt on the TV.

## Re-pair after a lost key

If the TV stops accepting the stored [[term:Pairing key]], Home Assistant starts reauthentication. Open the notification, select **Submit** and accept the new prompt on the TV.

## Change the host

If the IP address of the TV changes, discovery updates the entry. To change it by hand, open the config entry, choose the three-dot menu and select **Reconfigure**. Enter the new host. The flow aborts with `wrong_device` when the TV at that address is not the one that was configured.

## Setup messages

| Message | Cause | Fix |
| --- | --- | --- |
| `Failed to connect, please turn on your TV and try again.` | The TV is off or unreachable. | Turn the TV on and check that Home Assistant can reach its address. |
| `Pairing failed, make sure to accept the pairing request on the TV and try again.` | The prompt was declined or timed out. | Submit again and accept the prompt on the TV in time. |
| `Device is already configured` | The TV has an entry already. | Open the existing entry instead. |

:::see-also
- [[guides/turn-on]]
- [[reference/options]]
- [[guides/troubleshoot]]
:::
