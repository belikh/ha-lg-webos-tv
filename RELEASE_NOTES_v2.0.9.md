# Release notes: v2.0.9

**LG WebOS TV (bscpylgtv) for Home Assistant**

Version 2.0.9 fixes the current channel staying `unknown` after you switch
back to Live TV. No configuration changes are required; upgrade via the
Marketplace or HACS and restart Home Assistant.

## Current channel stays unknown

When you leave Live TV and return, the TV sends an error through the old
channel subscription (`broadcastId ... is already closed`). The bscpylgtv
library stores that error as the current channel and does not subscribe again,
so `current_channel` stayed `unknown`. The retry added in 2.0.8 treated the
stored error as a channel and never ran (issue #17).

The coordinator now:

- counts a channel only when it has a channel number or name,
- subscribes again when Live TV is in the foreground without a channel,
- reads the channel once with `get_current_channel` if the subscription sends none,
- retries up to 15 times, 2 seconds apart (was 6).

Checked on an LG TV playing an IPTV channel: HDMI 3 to Live TV left the sensor
`unknown` for 50 seconds on 2.0.8 and filled it in about 4 seconds on 2.0.9.

## Temporary workaround

The cause is in the library. The fix is proposed upstream in
[chros73/bscpylgtv#12](https://github.com/chros73/bscpylgtv/pull/12). This
integration will drop its workaround after a bscpylgtv release includes it.

## Thanks

- **@fast2doc**: issue #17, with the report that 2.0.8 did not fix it.
- **chros73**, author of the
  [bscpylgtv](https://github.com/chros73/bscpylgtv) library this integration
  is built on.
