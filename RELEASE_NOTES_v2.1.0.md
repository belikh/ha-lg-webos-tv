# Release notes: v2.1.0

**LG WebOS TV (bscpylgtv) for Home Assistant**

Upgrade via the Marketplace or HACS and restart Home Assistant.

## Library fork

The integration depends on the `belikh/bscpylgtv` fork (0.5.5.post1). Home
Assistant installs it automatically from the repository's release archive. The
fork fixes a deadlock in `bscpylgtv` 0.5.5 and stays in use until
chros73/bscpylgtv#13 is merged upstream.

## Fixes

- **Standby hang (#19).** When the TV turned off, the library awaited
  `disconnect()` inside its power-state callback and the client stopped
  updating. The log showed `Task was destroyed but it is pending`. Two users
  confirmed the errors are gone.
- **Turning off a TV that is off (#21).** `turn_off` on the media player and
  the remote does nothing when the TV is already off or disconnected.
  Automations no longer fail with `Not connected, can't execute command`.

## Volume on soundbars (#20)

On `external_arc`, `external_optical` and `external_speaker` the media player
hides the volume slider and level, because the TV cannot read the soundbar.
Volume up, down and mute still reach the soundbar.

An experimental option, off by default, restores the slider by pressing the
volume keys. The level shown is an estimate. See "Soundbar volume" in the
README for the options.

## Thanks

- **@Mrr-Engineer** and **@fast2doc**: issue #19, and testing the fix.
- **@diegocjorge**: issues #20 and #21, and testing the soundbar option.
- **chros73**, author of the
  [bscpylgtv](https://github.com/chros73/bscpylgtv) library this integration
  is built on.
