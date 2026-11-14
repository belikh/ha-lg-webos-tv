---
title: Remove the integration
summary: Delete the config entry, uninstall the code and clean up old v1 files.
order: 70
audience: users
status: draft
---

1. Open **Settings > Devices & Services** and open the **LG WebOS TV (bscpylgtv)** entry.
2. Choose the three-dot menu, then **Delete**. This removes the config entry, its device and its entities.
3. To remove the code, uninstall through HACS or delete `custom_components/bscpylgtv`, then restart Home Assistant.
4. Optional: delete the pairing files that v1 left in `.storage/bscpylgtv_*.sqlite`.
