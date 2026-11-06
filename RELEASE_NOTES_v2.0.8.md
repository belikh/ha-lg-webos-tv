# Release notes: v2.0.8

**LG WebOS TV (bscpylgtv) for Home Assistant**

Version 2.0.8 fixes two Live TV issues. No configuration changes are required;
upgrade via the Marketplace or HACS and restart Home Assistant.

## Live TV reports `playing`

The media player reported `on` while Live TV was in the foreground, so the
Home Assistant media card hid the previous/next buttons. The state is now
`playing` for Live TV and stays `on` for every other source. The buttons map to
channel down and channel up (issue #18).

## Current channel stays unknown

The bscpylgtv library subscribes to the current channel once, when the
foreground app becomes Live TV. If the TV is not ready (for example right after
switching from an HDMI input), the call fails and the library does not retry, so
`current_channel` stayed `unknown`. The coordinator now retries up to 6 times,
2 seconds apart, until a channel arrives (issue #17).

Checked on an LG TV: after a fresh connection on HDMI 1, switching to Live TV
filled the channel sensor within 4 seconds. Version 2.0.6 left it `unknown`
for 40 seconds after powering on to HDMI 1 and switching to Live TV.

## Thanks

- **@fast2doc**: issues #17 and #18, including the tested `state` change.
- **chros73**, author of the
  [bscpylgtv](https://github.com/chros73/bscpylgtv) library this integration
  is built on.
- The **Home Assistant core `webostv` maintainers**, whose integration served
  as the architecture reference.
